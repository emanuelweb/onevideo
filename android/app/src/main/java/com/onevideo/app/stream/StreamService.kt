package com.onevideo.app.stream

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.onevideo.app.MainActivity
import com.onevideo.app.Prefs
import com.onevideo.app.R
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject

/** Estado observable por la UI (la Activity lo colecta como StateFlow). */
data class StreamUiState(
    val serviceRunning: Boolean = false,
    val wsConnected: Boolean = false,
    val cameraOn: Boolean = false,
    val facing: String = "back",
    val resolution: String = "720p",
    val fps: Int = 30,
    val bitrateKbps: Int = 2500,
    val measuredKbps: Int? = null,
    val battery: Int? = null,
    val tempC: Double? = null,
    val network: String? = null,
    val lastError: String? = null,
)

/**
 * Foreground service (tipo camera|microphone): dueño del WebSocket de comandos,
 * del publicador WebRTC y del bucle de telemetría. Se inicia SIEMPRE desde la
 * Activity visible (restricción de Android 14+ para FGS de cámara) y sobrevive
 * con la pantalla bloqueada.
 *
 * Toda operación sobre objetos WebRTC se serializa en [webrtcExecutor]
 * (un único hilo propio), incluida la ejecución de comandos remotos.
 */
class StreamService : Service(), CommandSocket.Listener {

    private lateinit var prefs: Prefs
    private lateinit var webrtcExecutor: ExecutorService
    private lateinit var publisher: WebRtcPublisher
    private var socket: CommandSocket? = null
    private var wakeLock: PowerManager.WakeLock? = null

    /**
     * true desde el inicio de onDestroy. Evita re-publicar la notificación durante
     * el teardown (quedaría huérfana tras morir el FGS) y les indica a los
     * productores tardíos (comandos de OkHttp, errores de cámara del HAL) que el
     * servicio ya se está apagando.
     */
    @Volatile
    private var destroying = false

    private val mainHandler = Handler(Looper.getMainLooper())

    private val telemetryTicker = object : Runnable {
        override fun run() {
            sendTelemetry()
            mainHandler.postDelayed(this, TELEMETRY_INTERVAL_MS)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        webrtcExecutor = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "onevideo-webrtc")
        }
        publisher = WebRtcPublisher(this, WhipClient(), onCameraFailure = ::handleCameraFailure)
        createNotificationChannel()
        updateUi {
            it.copy(
                serviceRunning = true,
                facing = prefs.facing,
                resolution = prefs.resolution,
                fps = prefs.fps,
                bitrateKbps = prefs.bitrateKbps,
            )
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // startForeground inmediato (ventana de 5 s). En un reinicio por START_STICKY
        // desde background el sistema puede vetar el tipo camera: en ese caso el
        // servicio se apaga limpio en vez de crashear.
        try {
            startInForeground()
        } catch (e: Exception) {
            Log.w(TAG, "startForeground rechazado (¿reinicio en background?): ${e.message}")
            stopSelf()
            return START_NOT_STICKY
        }

        if (intent?.action == ACTION_STOP_SERVICE) {
            runOnWebrtcThread { stopStreamingInternal(notifyStatus = true) }
            stopSelf()
            return START_NOT_STICKY
        }

        ensureSocket()

        when (intent?.action) {
            ACTION_CAMERA_ON -> runOnWebrtcThread { startStreamingInternal() }
            ACTION_CAMERA_OFF -> runOnWebrtcThread { stopStreamingInternal(notifyStatus = true) }
            // ACTION_START o reinicio del sistema (intent null): solo WS + telemetría.
        }

        mainHandler.removeCallbacks(telemetryTicker)
        mainHandler.post(telemetryTicker)
        return START_STICKY
    }

    override fun onDestroy() {
        destroying = true
        mainHandler.removeCallbacksAndMessages(null)
        socket?.stop()
        socket = null
        // El executor NO se apaga aquí: productores tardíos (comandos que OkHttp
        // entrega durante el handshake de cierre, errores de cámara del HAL)
        // podrían encolar tareas mientras dura el teardown y un execute() sobre un
        // executor apagado tumbaría el proceso. La propia tarea de limpieza lo
        // apaga al terminar; lo que se encole después igual corre y sale rápido
        // gracias a las guardas (socket null / isPublishing false).
        runOnWebrtcThread {
            stopStreamingInternal(notifyStatus = false)
            publisher.dispose()
            // Si algún notify() corrió después de que el sistema retirara la
            // notificación del FGS, quedaría una notificación huérfana: fuera.
            getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
            webrtcExecutor.shutdown()
        }
        releaseWakeLock()
        updateUi {
            it.copy(serviceRunning = false, wsConnected = false, cameraOn = false, measuredKbps = null)
        }
        super.onDestroy()
    }

    /** Encola en el executor de WebRTC; ignora tareas tardías si ya se apagó. */
    private fun runOnWebrtcThread(task: () -> Unit) {
        try {
            webrtcExecutor.execute(task)
        } catch (e: RejectedExecutionException) {
            Log.w(TAG, "Tarea descartada: el executor de WebRTC ya está apagado")
        }
    }

    // ------------------------------------------------------------------ WebSocket

    private fun ensureSocket() {
        if (socket != null) return
        val wsUrl = prefs.wsUrl ?: run {
            Log.e(TAG, "Sin ws_url: el dispositivo no está emparejado")
            stopSelf()
            return
        }
        socket = CommandSocket(wsUrl, this).also { it.start() }
    }

    override fun onWsConnected() {
        updateUi { it.copy(wsConnected = true) }
        // Estado fresco apenas reconecta, para que el dashboard no espere 5 s.
        sendTelemetry()
    }

    override fun onWsDisconnected() {
        updateUi { it.copy(wsConnected = false) }
    }

    override fun onCommand(commandId: String, type: String, payload: JSONObject?) {
        if (destroying) return
        // Los comandos tocan cámara/PeerConnection: van al único hilo de WebRTC.
        runOnWebrtcThread { executeCommand(commandId, type, payload) }
    }

    // ------------------------------------------------------------------ Comandos

    /** Corre en el hilo de WebRTC. SIEMPRE responde ack con el mismo command_id. */
    private fun executeCommand(commandId: String, type: String, payload: JSONObject?) {
        val ws = socket ?: return
        try {
            when (type) {
                "camera_on" -> {
                    if (!publisher.isPublishing) startStreamingInternal()
                    ackFromState(ws, commandId)
                }
                "camera_off" -> {
                    stopStreamingInternal(notifyStatus = true)
                    ws.sendAck(commandId, ok = true)
                }
                "switch_camera" -> {
                    val facing = if (publisher.isPublishing) {
                        publisher.switchCamera()
                    } else {
                        if (prefs.facing == "back") "front" else "back"
                    }
                    prefs.facing = facing
                    updateUi { it.copy(facing = facing) }
                    sendTelemetryNow()
                    ws.sendAck(commandId, ok = true)
                }
                "set_quality" -> handleSetQuality(ws, commandId, payload)
                "torch_on" -> handleTorch(ws, commandId, on = true)
                "torch_off" -> handleTorch(ws, commandId, on = false)
                "restart_stream" -> {
                    if (publisher.isPublishing) {
                        stopStreamingInternal(notifyStatus = false)
                        startStreamingInternal()
                        ackFromState(ws, commandId)
                    } else {
                        ws.sendAck(commandId, ok = false, error = "No hay una transmisión activa para reiniciar.")
                    }
                }
                else -> ws.sendAck(commandId, ok = false, error = "Comando no reconocido: $type")
            }
        } catch (e: Exception) {
            ws.sendAck(commandId, ok = false, error = e.message ?: "Error interno al ejecutar el comando.")
        }
    }

    /** Ack de camera_on/restart según el resultado real del arranque. */
    private fun ackFromState(ws: CommandSocket, commandId: String) {
        if (publisher.isPublishing) {
            ws.sendAck(commandId, ok = true)
        } else {
            ws.sendAck(
                commandId,
                ok = false,
                error = _uiState.value.lastError ?: "No se pudo iniciar la transmisión.",
            )
        }
    }

    private fun handleSetQuality(ws: CommandSocket, commandId: String, payload: JSONObject?) {
        val resolution = payload?.optString("resolution").orEmpty()
        val fps = payload?.optInt("fps", -1) ?: -1
        val bitrateKbps = payload?.optInt("bitrate_kbps", -1) ?: -1
        if (resolution !in setOf("720p", "1080p") || fps !in setOf(30, 60) || bitrateKbps <= 0) {
            ws.sendAck(commandId, ok = false, error = "Parámetros de calidad inválidos.")
            return
        }
        if (publisher.isPublishing) {
            publisher.applyQuality(resolution, fps, bitrateKbps)
        }
        prefs.resolution = resolution
        prefs.fps = fps
        prefs.bitrateKbps = bitrateKbps
        updateUi { it.copy(resolution = resolution, fps = fps, bitrateKbps = bitrateKbps) }
        sendTelemetryNow()
        ws.sendAck(commandId, ok = true)
    }

    private fun handleTorch(ws: CommandSocket, commandId: String, on: Boolean) {
        if (publisher.isPublishing) {
            // setTorchMode solo funciona si la app no tiene la cámara abierta.
            ws.sendAck(
                commandId,
                ok = false,
                error = "La linterna no está disponible mientras se transmite (limitación de esta versión).",
            )
            return
        }
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            val backWithFlash = cameraManager.cameraIdList.firstOrNull { id ->
                val characteristics = cameraManager.getCameraCharacteristics(id)
                characteristics.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK &&
                    characteristics.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            }
            if (backWithFlash == null) {
                ws.sendAck(commandId, ok = false, error = "El dispositivo no tiene linterna disponible.")
                return
            }
            cameraManager.setTorchMode(backWithFlash, on)
            ws.sendAck(commandId, ok = true)
        } catch (e: Exception) {
            ws.sendAck(commandId, ok = false, error = "No se pudo cambiar la linterna: ${e.message ?: "error del sistema"}.")
        }
    }

    // ------------------------------------------------------------------ Streaming

    /** Corre en el hilo de WebRTC. */
    private fun startStreamingInternal() {
        if (publisher.isPublishing) return
        val token = prefs.deviceToken
        val whipUrl = prefs.whipUrl
        if (token == null || whipUrl == null) {
            updateUi { it.copy(lastError = getString(R.string.error_not_paired)) }
            return
        }
        val config = StreamConfig(
            resolution = prefs.resolution,
            fps = prefs.fps,
            bitrateKbps = prefs.bitrateKbps,
            facing = prefs.facing,
        )
        try {
            publisher.start(config, token, whipUrl)
            acquireWakeLock()
            updateUi { it.copy(cameraOn = true, lastError = null, facing = config.facing) }
            updateNotification(streaming = true)
        } catch (e: Exception) {
            val message = e.message ?: getString(R.string.error_stream_generic)
            Log.w(TAG, "Fallo al publicar: $message")
            updateUi { it.copy(cameraOn = false, lastError = message) }
            updateNotification(streaming = false)
        }
        // Telemetría inmediata al cambiar el estado de cámara (éxito o fallo).
        sendTelemetryNow()
    }

    /** Corre en el hilo de WebRTC. */
    private fun stopStreamingInternal(notifyStatus: Boolean) {
        if (publisher.isPublishing) {
            publisher.stop()
        }
        releaseWakeLock()
        updateUi { it.copy(cameraOn = false, measuredKbps = null) }
        updateNotification(streaming = false)
        if (notifyStatus) sendTelemetryNow()
    }

    /** Pérdida de cámara/ICE reportada por libwebrtc (hilo arbitrario). */
    private fun handleCameraFailure(reason: String) {
        Log.w(TAG, "Fallo de captura: $reason")
        runOnWebrtcThread {
            if (!publisher.isPublishing) return@runOnWebrtcThread
            publisher.stop()
            releaseWakeLock()
            updateUi { it.copy(cameraOn = false, lastError = reason, measuredKbps = null) }
            updateNotification(streaming = false)
            // camera_on:false inmediato: el dashboard muestra la caída al instante.
            sendTelemetryNow()
        }
    }

    // ------------------------------------------------------------------ Telemetría

    /**
     * Envía `status` (cada 5 s desde el ticker e inmediatamente ante cambios de
     * cámara). Llamable desde cualquier hilo: despacha al executor de WebRTC
     * porque [sendTelemetryNow] consulta al publicador (getStats), y el contrato
     * de WebRtcPublisher exige el único hilo de WebRTC.
     */
    private fun sendTelemetry() {
        runOnWebrtcThread { sendTelemetryNow() }
    }

    /** Corre en el hilo de WebRTC. */
    private fun sendTelemetryNow() {
        val ws = socket ?: return
        val snapshot = Telemetry.snapshot(this)
        val cameraOn = publisher.isPublishing
        val config = publisher.currentConfig
        val facing = config?.facing ?: prefs.facing
        val resolutionLabel = config?.resolutionLabel
            ?: StreamConfig(prefs.resolution, prefs.fps, prefs.bitrateKbps, prefs.facing).resolutionLabel

        updateUi { it.copy(battery = snapshot.battery, tempC = snapshot.tempC, network = snapshot.network) }

        if (cameraOn) {
            publisher.sampleBitrateKbps { kbps ->
                updateUi { it.copy(measuredKbps = kbps) }
                ws.sendStatus(
                    Telemetry.buildStatusPayload(snapshot, kbps, resolutionLabel, facing, cameraOn = true),
                )
            }
        } else {
            ws.sendStatus(
                Telemetry.buildStatusPayload(snapshot, null, resolutionLabel, facing, cameraOn = false),
            )
        }
    }

    // ------------------------------------------------------------------ Sistema

    private fun startInForeground() {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        } else {
            0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(streaming = false), type)
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notif_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply { description = getString(R.string.notif_channel_description) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(streaming: Boolean): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, StreamService::class.java).setAction(ACTION_STOP_SERVICE),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_stream)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(
                getString(if (streaming) R.string.notif_streaming else R.string.notif_connected),
            )
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(0, getString(R.string.notif_action_stop), stopIntent)
            .build()
    }

    private fun updateNotification(streaming: Boolean) {
        // Durante el teardown, un notify() tardío re-publicaría la notificación
        // después de que el sistema retirara la del FGS, dejándola huérfana.
        if (destroying) return
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(streaming))
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "OneVideo:Stream").apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
    }

    private fun updateUi(transform: (StreamUiState) -> StreamUiState) {
        // update {} (CAS en bucle): hay escritores en varios hilos y un
        // read-modify-write sobre .value perdería actualizaciones concurrentes.
        _uiState.update(transform)
    }

    companion object {
        private const val TAG = "StreamService"
        private const val CHANNEL_ID = "onevideo_stream"
        private const val NOTIFICATION_ID = 1001
        private const val TELEMETRY_INTERVAL_MS = 5_000L

        const val ACTION_START = "com.onevideo.app.action.START"
        const val ACTION_CAMERA_ON = "com.onevideo.app.action.CAMERA_ON"
        const val ACTION_CAMERA_OFF = "com.onevideo.app.action.CAMERA_OFF"
        const val ACTION_STOP_SERVICE = "com.onevideo.app.action.STOP_SERVICE"

        private val _uiState = MutableStateFlow(StreamUiState())

        /** Estado vivo del servicio para la UI. */
        val uiState: StateFlow<StreamUiState> = _uiState

        /** Arranca el servicio en foreground. Llamar SOLO con la Activity visible. */
        fun start(context: Context, action: String = ACTION_START) {
            val intent = Intent(context, StreamService::class.java).setAction(action)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, StreamService::class.java))
        }
    }
}

package com.onevideo.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.ViewFlipper
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.chip.Chip
import com.onevideo.app.net.PairingApi
import com.onevideo.app.net.PairingException
import com.onevideo.app.stream.StreamService
import com.onevideo.app.stream.StreamUiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Única Activity: pantalla de emparejamiento o de control según haya credenciales.
 * El servicio de streaming se inicia SIEMPRE desde aquí (Activity visible), como
 * exige Android 14+ para foreground services de cámara.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private lateinit var flipper: ViewFlipper

    // Emparejamiento
    private lateinit var inputServer: EditText
    private lateinit var inputCode: EditText
    private lateinit var btnPair: Button
    private lateinit var pairProgress: ProgressBar
    private lateinit var pairError: TextView

    // Control
    private lateinit var chipService: Chip
    private lateinit var chipWs: Chip
    private lateinit var chipCamera: Chip
    private lateinit var btnToggle: Button
    private lateinit var streamingBadge: TextView
    private lateinit var textQuality: TextView
    private lateinit var textTelemetry: TextView
    private lateinit var textError: TextView
    private lateinit var btnBattery: Button
    private lateinit var btnUnpair: Button

    /** true → al terminar la petición de permisos, encender también la cámara. */
    private var pendingCameraOn = false

    /**
     * true → arrancar el servicio en el próximo onStart. Se usa cuando el
     * emparejamiento resuelve con la app en background: startForegroundService
     * con permisos ya concedidos lanzaría ForegroundServiceStartNotAllowedException
     * (API 31+), así que el arranque se pospone hasta volver a primer plano.
     */
    private var pendingServiceStart = false

    private val permissionsLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
            val essentialGranted = results.filterKeys { it != Manifest.permission.POST_NOTIFICATIONS }
                .values.all { it }
            if (essentialGranted) {
                startService(cameraOn = pendingCameraOn)
            } else {
                textError.text = getString(R.string.error_permissions)
                textError.visibility = View.VISIBLE
            }
            pendingCameraOn = false
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        setContentView(R.layout.activity_main)
        bindViews()
        wireEvents()
        observeServiceState()

        if (prefs.isPaired) {
            showControl()
            ensurePermissionsAndStart(cameraOn = false)
        } else {
            showPairing()
        }
    }

    private fun bindViews() {
        flipper = findViewById(R.id.viewFlipper)
        inputServer = findViewById(R.id.inputServer)
        inputCode = findViewById(R.id.inputCode)
        btnPair = findViewById(R.id.btnPair)
        pairProgress = findViewById(R.id.pairProgress)
        pairError = findViewById(R.id.pairError)
        chipService = findViewById(R.id.chipService)
        chipWs = findViewById(R.id.chipWs)
        chipCamera = findViewById(R.id.chipCamera)
        btnToggle = findViewById(R.id.btnToggle)
        streamingBadge = findViewById(R.id.streamingBadge)
        textQuality = findViewById(R.id.textQuality)
        textTelemetry = findViewById(R.id.textTelemetry)
        textError = findViewById(R.id.textError)
        btnBattery = findViewById(R.id.btnBattery)
        btnUnpair = findViewById(R.id.btnUnpair)

        inputServer.setText(prefs.serverBase)
    }

    private fun wireEvents() {
        btnPair.setOnClickListener { pair() }
        btnToggle.setOnClickListener { toggleStreaming() }
        btnBattery.setOnClickListener { requestBatteryExemption() }
        btnUnpair.setOnClickListener { confirmUnpair() }
    }

    // ------------------------------------------------------------ Emparejamiento

    private fun pair() {
        val server = inputServer.text.toString().trim()
        val code = inputCode.text.toString().trim().uppercase()
        if (server.isEmpty() || code.length != 8) {
            pairError.text = getString(R.string.error_code_format)
            pairError.visibility = View.VISIBLE
            return
        }
        pairError.visibility = View.GONE
        btnPair.isEnabled = false
        pairProgress.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    PairingApi.claim(server, code, Build.MODEL ?: "Android")
                }
                prefs.serverBase = PairingApi.normalizeBase(server)
                prefs.deviceId = result.deviceId
                prefs.deviceToken = result.deviceToken
                prefs.whipUrl = result.whipUrl
                prefs.wsUrl = result.wsUrl
                inputCode.setText("")
                showControl()
                if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                    ensurePermissionsAndStart(cameraOn = false)
                } else {
                    pendingServiceStart = true
                }
            } catch (e: PairingException) {
                pairError.text = e.message
                pairError.visibility = View.VISIBLE
            } finally {
                btnPair.isEnabled = true
                pairProgress.visibility = View.GONE
            }
        }
    }

    // ------------------------------------------------------------------ Control

    private fun toggleStreaming() {
        val state = StreamService.uiState.value
        if (state.cameraOn) {
            StreamService.start(this, StreamService.ACTION_CAMERA_OFF)
        } else {
            ensurePermissionsAndStart(cameraOn = true)
        }
    }

    private fun ensurePermissionsAndStart(cameraOn: Boolean) {
        val required = mutableListOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            required += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = required.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            startService(cameraOn)
            return
        }
        pendingCameraOn = cameraOn
        permissionsLauncher.launch(missing.toTypedArray())
    }

    override fun onStart() {
        super.onStart()
        if (pendingServiceStart) {
            pendingServiceStart = false
            ensurePermissionsAndStart(cameraOn = false)
        }
    }

    private fun startService(cameraOn: Boolean) {
        val action = if (cameraOn) StreamService.ACTION_CAMERA_ON else StreamService.ACTION_START
        try {
            StreamService.start(this, action)
        } catch (e: IllegalStateException) {
            // ForegroundServiceStartNotAllowedException (API 31+): la app quedó en
            // background en el instante del arranque; reintentar al volver.
            pendingServiceStart = true
        }
    }

    private fun observeServiceState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                StreamService.uiState.collect { render(it) }
            }
        }
    }

    @SuppressLint("SetTextI18n")
    private fun render(state: StreamUiState) {
        chipService.text = getString(
            if (state.serviceRunning) R.string.chip_service_on else R.string.chip_service_off,
        )
        chipWs.text = getString(
            if (state.wsConnected) R.string.chip_ws_on else R.string.chip_ws_off,
        )
        chipCamera.text = getString(
            if (state.cameraOn) R.string.chip_camera_on else R.string.chip_camera_off,
        )

        btnToggle.text = getString(
            if (state.cameraOn) R.string.btn_stop_streaming else R.string.btn_start_streaming,
        )
        streamingBadge.visibility = if (state.cameraOn) View.VISIBLE else View.GONE

        val facingLabel = getString(
            if (state.facing == "front") R.string.facing_front else R.string.facing_back,
        )
        textQuality.text =
            "$facingLabel · ${state.resolution} · ${state.fps} fps · ${state.bitrateKbps} kbps"

        val parts = mutableListOf<String>()
        state.battery?.let { parts += getString(R.string.telemetry_battery, it) }
        state.tempC?.let { parts += getString(R.string.telemetry_temp, it) }
        state.network?.let { parts += getString(R.string.telemetry_network, it) }
        state.measuredKbps?.let { parts += getString(R.string.telemetry_bitrate, it) }
        textTelemetry.text = if (parts.isEmpty()) {
            getString(R.string.telemetry_empty)
        } else {
            parts.joinToString(" · ")
        }

        if (state.lastError != null) {
            textError.text = state.lastError
            textError.visibility = View.VISIBLE
        } else {
            textError.visibility = View.GONE
        }
    }

    // ------------------------------------------------------------------ Batería

    private fun requestBatteryExemption() {
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        if (powerManager.isIgnoringBatteryOptimizations(packageName)) {
            textError.visibility = View.GONE
            btnBattery.text = getString(R.string.btn_battery_done)
            return
        }
        // Intent directo con fallback a la pantalla general de ajustes.
        val direct = Intent(
            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:$packageName"),
        )
        try {
            startActivity(direct)
        } catch (e: Exception) {
            try {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (e2: Exception) {
                textError.text = getString(R.string.error_battery_settings)
                textError.visibility = View.VISIBLE
            }
        }
    }

    // ------------------------------------------------------------- Desemparejar

    private fun confirmUnpair() {
        AlertDialog.Builder(this)
            .setTitle(R.string.unpair_title)
            .setMessage(R.string.unpair_message)
            .setPositiveButton(R.string.unpair_confirm) { _, _ -> unpair() }
            .setNegativeButton(R.string.unpair_cancel, null)
            .show()
    }

    private fun unpair() {
        StreamService.stop(this)
        prefs.clearPairing()
        inputServer.setText(prefs.serverBase)
        showPairing()
    }

    // ---------------------------------------------------------------- Navegación

    private fun showPairing() {
        flipper.displayedChild = 0
    }

    private fun showControl() {
        flipper.displayedChild = 1
    }
}

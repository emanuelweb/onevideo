package com.onevideo.app.stream

import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.random.Random
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/**
 * WebSocket de comandos contra el backend (OkHttp) con reconexión automática.
 *
 * Protocolo (sobre JSON `{"type":..., "payload":...}`):
 *  - Servidor→App: `{"type":"command","payload":{"command_id","type","payload"}}`
 *    (el tipo del comando viaja DENTRO de payload).
 *  - App→Servidor: `ack` y `status` vía [sendAck] / [sendStatus].
 *
 * Backoff exponencial 1, 2, 4, 8, 16, 30 s (máx) + jitter, mientras [start]ed.
 * Los callbacks llegan en hilos de OkHttp; el consumidor decide dónde despachar.
 */
class CommandSocket(
    private val wsUrl: String,
    private val listener: Listener,
) {

    interface Listener {
        fun onWsConnected()
        fun onWsDisconnected()
        fun onCommand(commandId: String, type: String, payload: JSONObject?)
    }

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS) // WS de larga vida: sin timeout de lectura
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    private val handler = Handler(Looper.getMainLooper())
    private val running = AtomicBoolean(false)

    /**
     * Serializa la asignación de [webSocket] con las guardas de identidad de los
     * callbacks: OkHttp arranca la conexión en su propio hilo, así que sin el lock
     * un `onOpen` muy temprano podría comparar contra el campo aún sin asignar.
     */
    private val lock = Any()

    @Volatile
    private var webSocket: WebSocket? = null

    @Volatile
    var isConnected: Boolean = false
        private set

    private var attempt = 0

    fun start() {
        if (!running.compareAndSet(false, true)) return
        attempt = 0
        connect()
    }

    fun stop() {
        running.set(false)
        handler.removeCallbacksAndMessages(null)
        synchronized(lock) {
            webSocket?.close(1000, "cierre normal")
            webSocket = null
            isConnected = false
        }
    }

    fun sendAck(commandId: String, ok: Boolean, error: String? = null) {
        val payload = JSONObject().put("command_id", commandId).put("ok", ok)
        if (!ok) payload.put("error", error ?: "Error desconocido")
        send(JSONObject().put("type", "ack").put("payload", payload))
    }

    fun sendStatus(payload: JSONObject) {
        send(JSONObject().put("type", "status").put("payload", payload))
    }

    private fun send(message: JSONObject) {
        webSocket?.send(message.toString())
    }

    private fun connect() {
        if (!running.get()) return
        val request = Request.Builder().url(wsUrl).build()
        synchronized(lock) {
            webSocket = client.newWebSocket(request, socketListener)
        }
    }

    private fun scheduleReconnect() {
        if (!running.get()) return
        val delaySeconds = BACKOFF_SECONDS[minOf(attempt, BACKOFF_SECONDS.lastIndex)]
        attempt++
        val jitterMs = Random.nextLong(0, 1000)
        handler.postDelayed({ connect() }, delaySeconds * 1000L + jitterMs)
    }

    private val socketListener = object : WebSocketListener() {

        override fun onOpen(webSocket: WebSocket, response: Response) {
            synchronized(lock) {
                if (this@CommandSocket.webSocket !== webSocket) return // socket viejo
                isConnected = true
                attempt = 0
            }
            // Fuera del lock: el listener puede hacer trabajo arbitrario.
            listener.onWsConnected()
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val message = try {
                JSONObject(text)
            } catch (e: Exception) {
                return
            }
            if (message.optString("type") != "command") return
            val envelope = message.optJSONObject("payload") ?: return
            val commandId = envelope.optString("command_id")
            val commandType = envelope.optString("type")
            if (commandId.isBlank() || commandType.isBlank()) return
            listener.onCommand(commandId, commandType, envelope.optJSONObject("payload"))
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(1000, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            handleDisconnect(webSocket)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.w(TAG, "Fallo de WebSocket: ${t.message}")
            handleDisconnect(webSocket)
        }

        private fun handleDisconnect(closed: WebSocket) {
            val wasConnected: Boolean
            synchronized(lock) {
                // Eventos de sockets viejos (reemplazados por una reconexión) se ignoran
                // para no programar reconexiones duplicadas.
                if (this@CommandSocket.webSocket !== closed) return
                this@CommandSocket.webSocket = null
                wasConnected = isConnected
                isConnected = false
            }
            if (wasConnected) listener.onWsDisconnected()
            scheduleReconnect()
        }
    }

    companion object {
        private const val TAG = "CommandSocket"
        private val BACKOFF_SECONDS = intArrayOf(1, 2, 4, 8, 16, 30)
    }
}

package com.onevideo.app.stream

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import org.json.JSONObject

/** Instantánea de telemetría del dispositivo (todos los campos son opcionales). */
data class TelemetrySnapshot(
    val battery: Int?,
    val tempC: Double?,
    val charging: Boolean?,
    val network: String?,
)

/**
 * Lector de batería/térmica/red para el mensaje `status`.
 * El bitrate medido lo aporta [WebRtcPublisher] (delta de getStats).
 */
object Telemetry {

    fun snapshot(context: Context): TelemetrySnapshot {
        val batteryIntent: Intent? =
            context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))

        var battery: Int? = null
        var tempC: Double? = null
        var charging: Boolean? = null
        if (batteryIntent != null) {
            val level = batteryIntent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale = batteryIntent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            if (level >= 0 && scale > 0) battery = level * 100 / scale
            val tempTenths = batteryIntent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
            if (tempTenths != Int.MIN_VALUE) tempC = tempTenths / 10.0
            val status = batteryIntent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL
        }

        return TelemetrySnapshot(battery, tempC, charging, networkType(context))
    }

    private fun networkType(context: Context): String? {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return null
        val capabilities = cm.getNetworkCapabilities(cm.activeNetwork) ?: return "sin_red"
        return when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "celular"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "otra"
        }
    }

    /**
     * Construye el payload de `status` del protocolo. `camera_on` es el campo que hace
     * que el dashboard muestre «Transmitiendo»; siempre va incluido.
     */
    fun buildStatusPayload(
        snapshot: TelemetrySnapshot,
        bitrateKbps: Int?,
        resolution: String?,
        facing: String,
        cameraOn: Boolean,
    ): JSONObject {
        val payload = JSONObject()
        snapshot.battery?.let { payload.put("battery", it) }
        snapshot.tempC?.let { payload.put("temp_c", it) }
        snapshot.charging?.let { payload.put("charging", it) }
        snapshot.network?.let { payload.put("network", it) }
        bitrateKbps?.let { payload.put("bitrate_kbps", it) }
        resolution?.let { payload.put("resolution", it) }
        payload.put("facing", facing)
        payload.put("camera_on", cameraOn)
        return payload
    }
}

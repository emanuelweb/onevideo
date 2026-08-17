package com.onevideo.app

import android.content.Context
import android.content.SharedPreferences

/**
 * SharedPreferences tipadas de la app. Guarda credenciales de emparejamiento y los
 * ajustes de transmisión vigentes (el servidor no reenvía settings al conectar:
 * la app arranca con estos valores y el dashboard los ajusta con set_quality).
 */
class Prefs(context: Context) {

    private val sp: SharedPreferences =
        context.applicationContext.getSharedPreferences("onevideo_prefs", Context.MODE_PRIVATE)

    var serverBase: String
        get() = sp.getString(KEY_SERVER_BASE, DEFAULT_SERVER_BASE) ?: DEFAULT_SERVER_BASE
        set(value) = sp.edit().putString(KEY_SERVER_BASE, value).apply()

    var deviceId: String?
        get() = sp.getString(KEY_DEVICE_ID, null)
        set(value) = sp.edit().putString(KEY_DEVICE_ID, value).apply()

    var deviceToken: String?
        get() = sp.getString(KEY_DEVICE_TOKEN, null)
        set(value) = sp.edit().putString(KEY_DEVICE_TOKEN, value).apply()

    var whipUrl: String?
        get() = sp.getString(KEY_WHIP_URL, null)
        set(value) = sp.edit().putString(KEY_WHIP_URL, value).apply()

    var wsUrl: String?
        get() = sp.getString(KEY_WS_URL, null)
        set(value) = sp.edit().putString(KEY_WS_URL, value).apply()

    val isPaired: Boolean
        get() = deviceToken != null && whipUrl != null && wsUrl != null

    // Ajustes de transmisión (defaults del contrato: 720p, 30 fps, 2500 kbps, trasera).

    var resolution: String
        get() = sp.getString(KEY_RESOLUTION, "720p") ?: "720p"
        set(value) = sp.edit().putString(KEY_RESOLUTION, value).apply()

    var fps: Int
        get() = sp.getInt(KEY_FPS, 30)
        set(value) = sp.edit().putInt(KEY_FPS, value).apply()

    var bitrateKbps: Int
        get() = sp.getInt(KEY_BITRATE_KBPS, 2500)
        set(value) = sp.edit().putInt(KEY_BITRATE_KBPS, value).apply()

    var facing: String
        get() = sp.getString(KEY_FACING, "back") ?: "back"
        set(value) = sp.edit().putString(KEY_FACING, value).apply()

    /** Borra credenciales y ajustes (desemparejar). Conserva el servidor editado. */
    fun clearPairing() {
        sp.edit()
            .remove(KEY_DEVICE_ID)
            .remove(KEY_DEVICE_TOKEN)
            .remove(KEY_WHIP_URL)
            .remove(KEY_WS_URL)
            .remove(KEY_RESOLUTION)
            .remove(KEY_FPS)
            .remove(KEY_BITRATE_KBPS)
            .remove(KEY_FACING)
            .apply()
    }

    companion object {
        const val DEFAULT_SERVER_BASE = "http://onevideo-api-3e31e0-72-60-27-212.traefik.me"

        private const val KEY_SERVER_BASE = "server_base"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_TOKEN = "device_token"
        private const val KEY_WHIP_URL = "whip_url"
        private const val KEY_WS_URL = "ws_url"
        private const val KEY_RESOLUTION = "resolution"
        private const val KEY_FPS = "fps"
        private const val KEY_BITRATE_KBPS = "bitrate_kbps"
        private const val KEY_FACING = "facing"
    }
}

package com.onevideo.app.net

import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** Resultado exitoso de `POST /api/v1/pairing/claim`. */
data class PairingResult(
    val deviceId: String,
    val deviceToken: String,
    val whipUrl: String,
    val wsUrl: String,
)

/** Error de emparejamiento con mensaje listo para mostrar al usuario. */
class PairingException(message: String) : Exception(message)

object PairingApi {

    private val JSON = "application/json; charset=utf-8".toMediaType()

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    /**
     * Canjea el código de emparejamiento. Llamar desde un hilo de IO.
     * Lanza [PairingException] con mensaje en español ante cualquier fallo.
     */
    fun claim(serverBase: String, code: String, model: String): PairingResult {
        val base = normalizeBase(serverBase)
        val body = JSONObject()
            .put("code", code)
            .put("platform", "android")
            .put("model", model)
            .toString()
            .toRequestBody(JSON)

        val request = Request.Builder()
            .url("$base/api/v1/pairing/claim")
            .post(body)
            .build()

        val response = try {
            client.newCall(request).execute()
        } catch (e: IOException) {
            throw PairingException("No se pudo conectar con el servidor. Verifica la dirección y tu conexión.")
        }

        response.use {
            val text = it.body?.string().orEmpty()
            if (!it.isSuccessful) {
                throw PairingException(extractDetail(text) ?: "No se pudo emparejar (HTTP ${it.code}).")
            }
            return try {
                val json = JSONObject(text)
                PairingResult(
                    deviceId = json.getString("device_id"),
                    deviceToken = json.getString("device_token"),
                    whipUrl = json.getString("whip_url"),
                    wsUrl = json.getString("ws_url"),
                )
            } catch (e: Exception) {
                throw PairingException("Respuesta inesperada del servidor.")
            }
        }
    }

    /** Acepta entradas sin esquema (agrega http://) y quita la barra final. */
    fun normalizeBase(serverBase: String): String {
        var base = serverBase.trim().trimEnd('/')
        if (!base.contains("://")) base = "http://$base"
        return base
    }

    private fun extractDetail(body: String): String? = try {
        JSONObject(body).optString("detail").takeIf { it.isNotBlank() }
    } catch (e: Exception) {
        null
    }
}

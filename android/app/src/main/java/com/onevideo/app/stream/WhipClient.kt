package com.onevideo.app.stream

import java.io.IOException
import java.util.concurrent.TimeUnit
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** Error WHIP con mensaje en español listo para mostrar/ackear. */
class WhipException(message: String, val isAuthError: Boolean = false) : Exception(message)

/** Sesión WHIP publicada: SDP answer y URL de sesión (para el DELETE al parar). */
data class WhipSession(val answerSdp: String, val sessionUrl: String)

/**
 * Cliente WHIP mínimo: POST del offer (SDP completo, con ICE ya reunido) y
 * DELETE de la sesión al detener. Llamar siempre desde un hilo de fondo.
 */
class WhipClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    fun publish(whipUrl: String, deviceToken: String, offerSdp: String): WhipSession {
        val request = Request.Builder()
            .url(whipUrl)
            .header("Authorization", "Bearer $deviceToken")
            // Sobrecarga de ByteArray a propósito: la de String reescribe el MediaType
            // como "application/sdp; charset=utf-8" y MediaMTX exige el header exacto.
            .post(offerSdp.toByteArray(Charsets.UTF_8).toRequestBody(SDP))
            .build()

        val response = try {
            client.newCall(request).execute()
        } catch (e: IOException) {
            throw WhipException("No se pudo conectar con el servidor de video.")
        }

        response.use {
            val bodyText = it.body?.string().orEmpty()
            when {
                it.code == 401 -> {
                    // El backend puede devolver un detail legible (p. ej. horas del plan agotadas).
                    val detail = extractDetail(bodyText)
                    throw WhipException(
                        detail ?: "El servidor rechazó las credenciales del dispositivo.",
                        isAuthError = true,
                    )
                }
                !it.isSuccessful ->
                    throw WhipException("El servidor rechazó la publicación (HTTP ${it.code}).")
            }

            if (bodyText.isBlank()) throw WhipException("El servidor no devolvió una respuesta SDP.")

            val location = it.header("Location")
                ?: throw WhipException("El servidor no devolvió la URL de sesión (Location).")
            // Location puede ser relativa: resolver contra la URL WHIP.
            val sessionUrl = whipUrl.toHttpUrlOrNull()?.resolve(location)?.toString()
                ?: throw WhipException("URL de sesión inválida: $location")

            return WhipSession(answerSdp = bodyText, sessionUrl = sessionUrl)
        }
    }

    /** Cierra la sesión WHIP. Los fallos se ignoran: el servidor la expira sola. */
    fun delete(sessionUrl: String, deviceToken: String) {
        val request = Request.Builder()
            .url(sessionUrl)
            .header("Authorization", "Bearer $deviceToken")
            .delete()
            .build()
        try {
            client.newCall(request).execute().close()
        } catch (e: IOException) {
            // Sin red al parar: no es un error para el usuario.
        }
    }

    private fun extractDetail(body: String): String? = try {
        JSONObject(body).optString("detail").takeIf { it.isNotBlank() }
    } catch (e: Exception) {
        null
    }

    companion object {
        private val SDP = "application/sdp".toMediaType()
    }
}

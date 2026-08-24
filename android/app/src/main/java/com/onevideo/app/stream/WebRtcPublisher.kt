package com.onevideo.app.stream

import android.content.Context
import android.util.Log
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import org.webrtc.Camera2Enumerator
import org.webrtc.CameraVideoCapturer
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.MediaStreamTrack
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpTransceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper

/** Configuración vigente de captura/publicación. */
data class StreamConfig(
    val resolution: String, // "720p" | "1080p"
    val fps: Int,           // 30 | 60
    val bitrateKbps: Int,
    val facing: String,     // "front" | "back"
) {
    val width: Int get() = if (resolution == "1080p") 1920 else 1280
    val height: Int get() = if (resolution == "1080p") 1080 else 720
    val resolutionLabel: String get() = "${width}x$height"
}

/** Error de publicación con mensaje en español (para ack y UI). */
class PublishException(message: String, cause: Throwable? = null) : Exception(message, cause)

/**
 * Publicador WebRTC→WHIP.
 *
 * CONTRATO DE HILOS: todos los métodos públicos deben invocarse desde el ÚNICO
 * executor de WebRTC que posee StreamService. Los callbacks de libwebrtc llegan
 * en sus hilos internos y se puentean con latches/volatiles; nunca se manipulan
 * los objetos de PeerConnection desde otros hilos.
 */
class WebRtcPublisher(
    private val appContext: Context,
    private val whipClient: WhipClient,
    /** Aviso de pérdida de cámara (OEM/HAL); llega en un hilo interno de la cámara. */
    private val onCameraFailure: (String) -> Unit,
) {

    private val eglBase: EglBase = EglBase.create()

    private val factory: PeerConnectionFactory by lazy {
        ensureInitialized(appContext)
        PeerConnectionFactory.builder()
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true))
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(eglBase.eglBaseContext))
            .createPeerConnectionFactory()
    }

    private var peerConnection: PeerConnection? = null
    private var capturer: CameraVideoCapturer? = null
    private var surfaceTextureHelper: SurfaceTextureHelper? = null
    private var videoSource: org.webrtc.VideoSource? = null
    private var audioSource: org.webrtc.AudioSource? = null
    private var videoTrack: org.webrtc.VideoTrack? = null
    private var audioTrack: org.webrtc.AudioTrack? = null
    private var sessionUrl: String? = null
    private var deviceToken: String? = null

    /** Para el cálculo de bitrate por delta de getStats. */
    private var lastBytesSent: Long = -1
    private var lastStatsAtMs: Long = 0

    @Volatile
    var isPublishing: Boolean = false
        private set

    @Volatile
    var currentConfig: StreamConfig? = null
        private set

    /** Captura + oferta + WHIP. Lanza [PublishException] con mensaje en español. */
    fun start(config: StreamConfig, token: String, whipUrl: String) {
        check(!isPublishing) { "Ya se está publicando" }
        deviceToken = token
        try {
            startInternal(config, token, whipUrl)
            isPublishing = true
            currentConfig = config
        } catch (e: Exception) {
            releaseSession()
            when (e) {
                is PublishException, is WhipException -> throw e
                else -> throw PublishException("No se pudo iniciar la transmisión: ${e.message}", e)
            }
        }
    }

    private fun startInternal(config: StreamConfig, token: String, whipUrl: String) {
        val enumerator = Camera2Enumerator(appContext)
        val deviceName = pickCamera(enumerator, config.facing)
            ?: throw PublishException("No se encontró una cámara compatible en el dispositivo.")

        val cameraCapturer = enumerator.createCapturer(deviceName, cameraEventsHandler)
            ?: throw PublishException("No se pudo abrir la cámara seleccionada.")
        capturer = cameraCapturer

        val source = factory.createVideoSource(cameraCapturer.isScreencast)
        videoSource = source
        val helper = SurfaceTextureHelper.create("OneVideoCapture", eglBase.eglBaseContext)
        surfaceTextureHelper = helper
        cameraCapturer.initialize(helper, appContext, source.capturerObserver)
        cameraCapturer.startCapture(config.width, config.height, config.fps)

        val audioConstraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "true"))
        }
        val audio = factory.createAudioSource(audioConstraints)
        audioSource = audio

        val vTrack = factory.createVideoTrack("onevideo-video", source)
        val aTrack = factory.createAudioTrack("onevideo-audio", audio)
        videoTrack = vTrack
        audioTrack = aTrack

        val rtcConfig = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            // GATHER_ONCE: el gathering llega a COMPLETE y ahí recién se hace el POST WHIP.
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_ONCE
        }

        val gatheringComplete = CountDownLatch(1)
        val pc = factory.createPeerConnection(rtcConfig, object : PeerConnectionObserverAdapter() {
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                if (state == PeerConnection.IceGatheringState.COMPLETE) gatheringComplete.countDown()
            }

            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {
                Log.i(TAG, "Estado ICE: $state")
                if (state == PeerConnection.IceConnectionState.FAILED && isPublishing) {
                    onCameraFailure("Se perdió la conexión de video con el servidor.")
                }
            }
        }) ?: throw PublishException("No se pudo crear la conexión WebRTC.")
        peerConnection = pc

        pc.addTrack(vTrack, listOf(STREAM_ID))
        pc.addTrack(aTrack, listOf(STREAM_ID))
        // Publicación pura: sin recepción.
        pc.transceivers.forEach { it.direction = RtpTransceiver.RtpTransceiverDirection.SEND_ONLY }

        // La grabación en la nube usa fMP4, que NO admite VP8: si el offer lleva VP8
        // primero, MediaMTX transmite bien pero graba solo el audio (video en negro).
        // Se ordena H264 al frente —todo celular lo trae por hardware— y se conservan
        // VP8/VP9 como respaldo para no romper la transmisión en encoders exóticos.
        val videoCodecs = factory
            .getRtpSenderCapabilities(MediaStreamTrack.MediaType.MEDIA_TYPE_VIDEO)
            .codecs
        if (videoCodecs.any { it.name.equals("H264", ignoreCase = true) }) {
            val preferred = videoCodecs.sortedByDescending { it.name.equals("H264", ignoreCase = true) }
            pc.transceivers
                .firstOrNull { it.mediaType == MediaStreamTrack.MediaType.MEDIA_TYPE_VIDEO }
                ?.setCodecPreferences(preferred)
        }

        applyMaxBitrate(config.bitrateKbps)

        val offer = awaitCreateOffer(pc)
        awaitSetDescription { observer -> pc.setLocalDescription(observer, offer) }

        // Estrategia ICE: reunir candidatos completos ANTES del POST (el servidor
        // devuelve los suyos en el answer; no hay trickle ni TURN).
        if (!gatheringComplete.await(ICE_GATHERING_TIMEOUT_S, TimeUnit.SECONDS)) {
            throw PublishException("No se pudieron reunir los candidatos de red (ICE). Revisa tu conexión.")
        }

        val localSdp = pc.localDescription?.description
            ?: throw PublishException("No se pudo generar la oferta SDP.")

        val session = whipClient.publish(whipUrl, token, localSdp)
        sessionUrl = session.sessionUrl

        awaitSetDescription { observer ->
            pc.setRemoteDescription(
                observer,
                SessionDescription(SessionDescription.Type.ANSWER, session.answerSdp),
            )
        }

        lastBytesSent = -1
        lastStatsAtMs = 0
    }

    /** Detiene captura y publicación (incluye el DELETE de la sesión WHIP). */
    fun stop() {
        isPublishing = false
        val url = sessionUrl
        val token = deviceToken
        if (url != null && token != null) whipClient.delete(url, token)
        releaseSession()
    }

    /** Cambia de lente en caliente. Devuelve el facing resultante ("front"/"back"). */
    fun switchCamera(): String {
        val cameraCapturer = capturer
            ?: throw PublishException("La cámara no está activa.")
        val result = AtomicReference<String?>(null)
        val done = CountDownLatch(1)
        cameraCapturer.switchCamera(object : CameraVideoCapturer.CameraSwitchHandler {
            override fun onCameraSwitchDone(isFrontCamera: Boolean) {
                result.set(if (isFrontCamera) "front" else "back")
                done.countDown()
            }

            override fun onCameraSwitchError(error: String?) {
                done.countDown()
            }
        })
        if (!done.await(5, TimeUnit.SECONDS) || result.get() == null) {
            throw PublishException("No se pudo cambiar de cámara.")
        }
        val facing = result.get()!!
        currentConfig = currentConfig?.copy(facing = facing)
        return facing
    }

    /** Aplica calidad en caliente: formato de captura + techo de bitrate del sender. */
    fun applyQuality(resolution: String, fps: Int, bitrateKbps: Int) {
        val cameraCapturer = capturer
            ?: throw PublishException("La cámara no está activa.")
        val newConfig = (currentConfig ?: return).copy(
            resolution = resolution,
            fps = fps,
            bitrateKbps = bitrateKbps,
        )
        cameraCapturer.changeCaptureFormat(newConfig.width, newConfig.height, newConfig.fps)
        applyMaxBitrate(bitrateKbps)
        currentConfig = newConfig
    }

    /**
     * Bitrate de salida medido (delta de bytesSent de getStats). El callback llega
     * en un hilo interno de libwebrtc; no tocar objetos WebRTC desde él.
     */
    fun sampleBitrateKbps(callback: (Int?) -> Unit) {
        val pc = peerConnection
        if (pc == null || !isPublishing) {
            callback(null)
            return
        }
        pc.getStats { report ->
            var bytesSent = 0L
            var found = false
            for (stats in report.statsMap.values) {
                if (stats.type == "outbound-rtp") {
                    val kind = stats.members["kind"] ?: stats.members["mediaType"]
                    if (kind == "video") {
                        (stats.members["bytesSent"] as? Number)?.let {
                            bytesSent += it.toLong()
                            found = true
                        }
                    }
                }
            }
            if (!found) {
                callback(null)
                return@getStats
            }
            val now = System.currentTimeMillis()
            val kbps = if (lastBytesSent >= 0 && now > lastStatsAtMs) {
                (((bytesSent - lastBytesSent) * 8) / (now - lastStatsAtMs)).toInt().coerceAtLeast(0)
            } else null
            lastBytesSent = bytesSent
            lastStatsAtMs = now
            callback(kbps)
        }
    }

    /** Libera la fábrica y el EGL. Llamar solo al morir el servicio. */
    fun dispose() {
        releaseSession()
        try {
            factory.dispose()
        } catch (e: Exception) {
            Log.w(TAG, "Error al liberar la fábrica: ${e.message}")
        }
        eglBase.release()
    }

    private fun applyMaxBitrate(bitrateKbps: Int) {
        val sender = peerConnection?.senders?.firstOrNull { it.track()?.kind() == "video" } ?: return
        val parameters = sender.parameters
        if (parameters.encodings.isEmpty()) return
        parameters.encodings[0].maxBitrateBps = bitrateKbps * 1000
        sender.setParameters(parameters)
    }

    private fun releaseSession() {
        sessionUrl = null
        try {
            capturer?.stopCapture()
        } catch (e: InterruptedException) {
            Thread.currentThread().interrupt()
        } catch (e: Exception) {
            Log.w(TAG, "Error al detener la captura: ${e.message}")
        }
        capturer?.dispose()
        capturer = null
        videoTrack?.dispose()
        videoTrack = null
        audioTrack?.dispose()
        audioTrack = null
        videoSource?.dispose()
        videoSource = null
        audioSource?.dispose()
        audioSource = null
        surfaceTextureHelper?.dispose()
        surfaceTextureHelper = null
        // dispose() (no solo close()): close() no libera el objeto nativo ni los
        // global refs JNI, y filtraría un PeerConnection por cada ciclo on/off.
        peerConnection?.dispose()
        peerConnection = null
        isPublishing = false
        currentConfig = null
    }

    private fun pickCamera(enumerator: Camera2Enumerator, facing: String): String? {
        val names = enumerator.deviceNames
        val preferred = names.firstOrNull {
            if (facing == "front") enumerator.isFrontFacing(it) else enumerator.isBackFacing(it)
        }
        return preferred ?: names.firstOrNull()
    }

    private fun awaitCreateOffer(pc: PeerConnection): SessionDescription {
        val result = AtomicReference<SessionDescription?>(null)
        val error = AtomicReference<String?>(null)
        val done = CountDownLatch(1)
        pc.createOffer(object : SdpObserverAdapter() {
            override fun onCreateSuccess(description: SessionDescription) {
                result.set(description)
                done.countDown()
            }

            override fun onCreateFailure(message: String?) {
                error.set(message)
                done.countDown()
            }
        }, MediaConstraints())
        if (!done.await(SDP_TIMEOUT_S, TimeUnit.SECONDS)) {
            throw PublishException("Tiempo de espera agotado al crear la oferta SDP.")
        }
        return result.get()
            ?: throw PublishException("No se pudo crear la oferta SDP: ${error.get() ?: "error interno"}")
    }

    private fun awaitSetDescription(call: (SdpObserver) -> Unit) {
        val error = AtomicReference<String?>(null)
        val failed = AtomicReference(false)
        val done = CountDownLatch(1)
        call(object : SdpObserverAdapter() {
            override fun onSetSuccess() {
                done.countDown()
            }

            override fun onSetFailure(message: String?) {
                failed.set(true)
                error.set(message)
                done.countDown()
            }
        })
        if (!done.await(SDP_TIMEOUT_S, TimeUnit.SECONDS)) {
            throw PublishException("Tiempo de espera agotado al aplicar la descripción SDP.")
        }
        if (failed.get()) {
            throw PublishException("Fallo al aplicar la descripción SDP: ${error.get() ?: "error interno"}")
        }
    }

    private val cameraEventsHandler = object : CameraVideoCapturer.CameraEventsHandler {
        override fun onCameraError(error: String?) {
            onCameraFailure("Error de cámara: ${error ?: "desconocido"}")
        }

        override fun onCameraDisconnected() {
            onCameraFailure("El sistema desconectó la cámara (posible restricción del fabricante).")
        }

        override fun onCameraFreezed(error: String?) {
            onCameraFailure("La cámara dejó de entregar imagen: ${error ?: "desconocido"}")
        }

        override fun onCameraOpening(cameraName: String?) {}
        override fun onFirstFrameAvailable() {}
        override fun onCameraClosed() {}
    }

    /** Adaptadores para no implementar interfaces completas en cada uso. */
    private open class SdpObserverAdapter : SdpObserver {
        override fun onCreateSuccess(description: SessionDescription) {}
        override fun onSetSuccess() {}
        override fun onCreateFailure(message: String?) {}
        override fun onSetFailure(message: String?) {}
    }

    private open class PeerConnectionObserverAdapter : PeerConnection.Observer {
        override fun onSignalingChange(state: PeerConnection.SignalingState) {}
        override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) {}
        override fun onIceConnectionReceivingChange(receiving: Boolean) {}
        override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {}
        override fun onIceCandidate(candidate: IceCandidate) {}
        override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) {}
        override fun onAddStream(stream: MediaStream) {}
        override fun onRemoveStream(stream: MediaStream) {}
        override fun onDataChannel(channel: org.webrtc.DataChannel) {}
        override fun onRenegotiationNeeded() {}
    }

    companion object {
        private const val TAG = "WebRtcPublisher"
        private const val STREAM_ID = "onevideo"
        private const val ICE_GATHERING_TIMEOUT_S = 10L
        private const val SDP_TIMEOUT_S = 10L

        @Volatile
        private var initialized = false

        fun ensureInitialized(context: Context) {
            if (initialized) return
            synchronized(this) {
                if (initialized) return
                PeerConnectionFactory.initialize(
                    PeerConnectionFactory.InitializationOptions.builder(context.applicationContext)
                        .createInitializationOptions(),
                )
                initialized = true
            }
        }
    }
}

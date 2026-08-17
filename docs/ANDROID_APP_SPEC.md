# OneVideo — Especificación técnica de la app Android (fase 2)

> Contrato de referencia: [CONTRACT.md](./CONTRACT.md) (§3 rutas de streaming, §4.
> emparejamiento, §5 WebSocket de dispositivo). Esta spec no redefine nada del contrato;
> lo implementa.

## 1. Objetivo

App Android que publica la cámara del celular por WHIP a MediaMTX y obedece comandos
remotos del dashboard, de forma continua y estable, **incluso con la pantalla bloqueada**,
dentro de lo que Android y cada OEM realmente permiten (ver §5 — hay límites duros y hay
que ser honestos con el usuario).

Mínimo soportado: **Android 8.0 (API 26)**. Objetivo de pruebas prioritario: Android 11–15,
que es donde viven las restricciones modernas de foreground service y cámara.

## 2. Stack

| Área | Elección | Por qué |
|---|---|---|
| Lenguaje | Kotlin (coroutines + Flow) | estándar actual; WS y telemetría son naturalmente reactivos |
| Cámara | **CameraX** (core), fallback a Camera2 directo donde CameraX limite (control fino de linterna/fps en algunos OEM) | CameraX absorbe la enorme variabilidad de HALs; Camera2 queda como escotilla |
| WebRTC | **libwebrtc** (prebuilt de google/webrtc) | encoder por hardware (MediaCodec), estimación de congestión, ICE — imposible de replicar a mano |
| Señalización | WHIP: un `POST` HTTP con SDP offer, respuesta SDP answer | es todo lo que WHIP exige; sin SDK de terceros |
| HTTP/WS | OkHttp (HTTP + WebSocket) | maduro, WS robusto, reintentos controlables |
| Persistencia | EncryptedSharedPreferences (Android Keystore) | el `device_token` es una credencial de larga vida |
| UI | Jetpack Compose, una sola Activity | la UI es mínima: pairing, preview, estado |

Pipeline de video: CameraX `Preview`/`ImageAnalysis` → `SurfaceTextureHelper` de libwebrtc
→ `VideoTrack` → `PeerConnection` (sendonly) → WHIP. Audio opcional (micrófono del
celular) como `AudioTrack`, desactivado por defecto en el MVP de la app.

## 3. Ciclo de vida principal

### 3.1 Emparejamiento
1. El usuario crea el dispositivo en el dashboard y ve un código de **8 caracteres A-Z0-9**
   (expira a los 15 min, un solo uso).
2. En la app lo ingresa y la app llama `POST {API}/api/v1/pairing/claim` con
   `{"code": "...", "platform": "android", "model": Build.MODEL}`.
3. Respuesta: `{device_id, device_token, whip_url, ws_url}`. El `device_token` se guarda
   en EncryptedSharedPreferences y **nunca** se muestra ni se loguea.
4. Si el código expiró o ya fue usado: mensaje claro en español y opción de reintentar
   (el dashboard puede regenerar código).

### 3.2 Servicio de streaming
Todo el trabajo vive en un **Foreground Service**:

- Manifest: `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CAMERA` (obligatorio en Android 14+),
  `CAMERA`, `RECORD_AUDIO` (si audio), `INTERNET`, `WAKE_LOCK`,
  `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (ver §5.3), y en el `<service>`:
  `android:foregroundServiceType="camera|microphone"`.
- El servicio se inicia **siempre con la app en primer plano** (tap del usuario o comando
  recibido con la app visible). Desde Android 11, un servicio con tipo `camera` iniciado
  en background **no recibe acceso a la cámara** (restricciones de while-in-use); por eso
  el flujo de UX exige abrir la app para armar la cámara. Una vez en marcha, el servicio
  sobrevive a que la app pase a background o la pantalla se bloquee.
- Notificación persistente con estado (transmitiendo / conectado / error), acción "Detener",
  y `setOngoing(true)`.
- Mientras transmite: **partial wake lock** (`PowerManager.PARTIAL_WAKE_LOCK`) para que el
  CPU no duerma con la pantalla apagada, y `WifiManager` lock si la red es WiFi.

### 3.3 Canal de control (WebSocket — contrato §5)
- Conexión: `GET {ws_url}?token=<device_token>` (el `ws_url` viene del pairing).
- **Device→Server `status`** cada 5 s y ante cualquier cambio relevante:
  `{"type":"status","payload":{battery, temp_c, charging, network, bitrate_kbps, resolution, facing, camera_on}}`.
- **Server→Device `command`**: `{command_id, type, payload}` con los tipos del contrato:
  `camera_on`, `camera_off`, `switch_camera`, `set_quality` (`{resolution, fps, bitrate_kbps}`),
  `torch_on`, `torch_off`, `restart_stream`.
- **Device→Server `ack`**: `{command_id, ok, error?}`. Un comando que el hardware no
  soporta (p. ej. linterna en cámara frontal) responde `ok:false` con `error` descriptivo,
  nunca silencio.
- Reconexión: backoff exponencial con jitter (1 s → 2 → 4 → … máx 60 s), sin límite de
  intentos mientras el servicio viva. El WS caído **no** detiene el video (WHIP es
  independiente); solo se pierde control remoto y telemetría hasta reconectar.

### 3.4 Publicación WHIP
1. Crear `PeerConnection` sendonly con el video track (y audio si aplica).
2. `createOffer` → `POST {whip_url}` con `Content-Type: application/sdp` y
   `Authorization: Bearer <device_token>` → answer SDP → `setRemoteDescription`.
3. Guardar el header `Location` de la respuesta para el teardown (`DELETE`) al detener.
4. Ante `401`: el token fue revocado o el plan agotó horas → estado visible en la app y
   `status` por WS; no reintentar en loop ciego (reintento lento cada 60 s).
5. Caída de ICE (`disconnected`/`failed`): intento de ICE restart; si no recupera en ~10 s,
   teardown y re-POST WHIP completo con backoff. El objetivo de reconexión total es < 15 s.

## 4. Calidad, bitrate adaptativo y térmica

### 4.1 Bitrate adaptativo
- libwebrtc ya trae estimación de ancho de banda (transport-cc); la app fija el techo con
  `RtpSender.parameters.encodings[0].maxBitrateBps` según el `set_quality` vigente.
- Escalera de degradación (en orden): bajar bitrate → bajar fps (60→30) → bajar resolución
  (1080p→720p). `degradationPreference = MAINTAIN_FRAMERATE` por defecto (para streaming
  en vivo la fluidez pesa más que la nitidez).
- Al recuperar red, subir en pasos (no de golpe) hasta el techo del plan.
- Presets según contrato: 720p/30 (free), 1080p/30 (creator), 1080p/60 (pro/studio).
  El enforcement es **cooperativo**: el server manda `set_quality` y la app obedece; el
  server no transcodifica.

### 4.2 Gestión térmica
Transmitir con encoder por hardware calienta el teléfono; es el límite práctico número uno
en sesiones largas.

- API 29+: `PowerManager.addThermalStatusListener`. API 30+: `getThermalHeadroom()`
  consultado cada ~30 s (con la cadencia mínima que la API tolera).
- Política escalonada:
  | Estado térmico | Acción |
  |---|---|
  | `MODERATE` / headroom > 0.85 | bajar bitrate 25 % |
  | `SEVERE` | forzar 720p/30, avisar por `status` (temp_c ya viaja en telemetría) |
  | `CRITICAL`+ | pausar video (mantener WS), notificar; reanudar al enfriar |
- Recomendaciones al usuario (en la UI y en la guía): **no cargar el teléfono mientras
  transmite** o usar carga lenta (cargar + encodear es la combinación que dispara la
  térmica), quitar la funda, evitar sol directo. La telemetría `charging` + `temp_c`
  permite al dashboard mostrar este consejo en el momento justo.

## 5. Pantalla bloqueada: qué es posible de verdad

Esta es la promesa central del producto, así que va con precisión:

- **Lo que Android permite**: desde Android 9, una app en background **sin** foreground
  service tiene la cámara bloqueada por el sistema. Un **foreground service con tipo
  `camera` iniciado mientras la app estaba en primer plano** conserva el acceso, y en la
  mayoría de los dispositivos **sigue capturando y transmitiendo con la pantalla apagada o
  bloqueada**. Este es el mecanismo en que se apoya OneVideo, y es el mismo que usan apps
  de dashcam y monitoreo publicadas en Play.
- **Lo que no está garantizado**: ningún documento de Android garantiza cámara con pantalla
  apagada; es comportamiento del HAL/OEM. Una minoría de dispositivos corta el feed de
  cámara al bloquear (o al rato), y algunos OEM matan el proceso completo pese al
  foreground service.
- **Consecuencia de diseño (obligatoria)**: la app debe **detectar** la pérdida de cámara
  (callback de error de CameraX/Camera2, o watchdog: cero frames entregados durante > 3 s)
  y **notificarlo** — actualización inmediata de `status` por WS con `camera_on:false`,
  para que el dashboard muestre "El dispositivo dejó de capturar" en vez de un stream
  congelado sin explicación. Con pantalla bloqueada tampoco existe preview local: el único
  monitor real es el dashboard/OBS, y la UI de la app debe decirlo explícitamente antes de
  que el usuario bloquee.

### 5.1 OEMs problemáticos
Xiaomi/MIUI-HyperOS, Huawei/EMUI, Oppo/ColorOS, Vivo y variantes matan servicios en
segundo plano con políticas propias que ignoran las exenciones estándar de Android.
Referencia viva: [dontkillmyapp.com](https://dontkillmyapp.com).

- La app incluye una pantalla "Mantener activa la transmisión" que detecta el fabricante
  (`Build.MANUFACTURER`) y muestra los pasos específicos (p. ej. MIUI: Autostart +
  "Sin restricciones" en batería + candado en recientes).
- En la primera sesión larga, si el proceso murió (detectable al relanzar: el servicio no
  llegó a un shutdown limpio), mostrar diagnóstico y volver a la guía del OEM.
- No prometemos milagros: en un Huawei con políticas agresivas sin configurar, la sesión
  **va a morir**. Mejor decirlo en la app que descubrirlo en vivo.

### 5.2 Wake locks
- Partial wake lock adquirido solo mientras el servicio transmite; liberado siempre en
  teardown (fugas de wake lock = desinstalación por batería).

### 5.3 Exención de optimización de batería
- Al activar por primera vez el modo "transmitir con pantalla bloqueada", pedir la exención
  con `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (permiso
  `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` en el manifest).
- Google Play acepta este permiso solo si la función central lo justifica; una app de
  cámara/transmisión continua es de los casos legítimos, pero hay que declararlo en la
  ficha de la Play Console y estar preparados para el rechazo inicial. Plan B siempre
  disponible: deep-link a `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS` (la pantalla de
  ajustes, sin permiso especial) con instrucciones.

## 6. Política de Play Store (foreground service `camera`)

- Android 14+: declarar `FOREGROUND_SERVICE_CAMERA` y el
  `foregroundServiceType="camera"`; en la Play Console hay que **declarar el uso del tipo
  de foreground service** con justificación y un video demo del flujo. Nuestra
  justificación: "transmisión de cámara en vivo iniciada explícitamente por el usuario,
  con notificación persistente y botón de detener" — caso de uso aceptado (streaming /
  captura continua).
- Divulgación prominente en la app: antes de la primera transmisión, texto claro de que la
  cámara sigue activa con la pantalla bloqueada mientras la notificación esté visible.
- La notificación persistente es innegociable (además de obligatoria): es la señal honesta
  de que la cámara está en uso, junto con el indicador verde del sistema (Android 12+).
- Data safety: el video va del dispositivo al servidor del usuario final (su stream); no
  se almacena en el MVP. Declararlo tal cual.

## 7. Estados y UI (mínima, en español)

Pantallas: **Emparejar** (código de 8 caracteres), **Principal** (preview local cuando la
pantalla está activa, estado de conexión WS/WHIP, calidad actual, temperatura, botón
grande iniciar/detener), **Mantener activa** (guía por OEM, §5.1), **Ajustes** (audio
on/off, cámara por defecto, servidor si algún día hay multi-nodo).

Máquina de estados del servicio:
`IDLE → CONNECTING (WS) → READY → PUBLISHING → (DEGRADED térmico/red) → RECONNECTING → PUBLISHING | STOPPED(razón)`
Cada transición se refleja en la notificación y en el `status` por WS.

## 8. Criterios de aceptación (fase 2)

1. Emparejar con código y transmitir a OBS vía la página player en < 2 min desde instalar.
2. 60 min continuos con pantalla bloqueada en un Pixel y un Samsung de gama media sin caída
   (con exención de batería activada).
3. Todos los comandos del contrato ejecutados desde el dashboard con `ack` correcto,
   incluida la negación honesta (`torch_on` en frontal → `ok:false`).
4. Corte de red de 30 s → recuperación automática de WS y WHIP en < 15 s tras volver la red.
5. Sesión con calentamiento inducido degrada calidad y lo reporta, sin morir.
6. Pérdida de cámara por OEM (simulada matando el proceso) → el dashboard muestra el
   dispositivo offline en < 40 s (timeout de WS + tracker).

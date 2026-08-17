# OneVideo — Roadmap

> Referencias: [CONTRACT.md](./CONTRACT.md) (contrato técnico),
> [ARQUITECTURA.md](./ARQUITECTURA.md), [ANDROID_APP_SPEC.md](./ANDROID_APP_SPEC.md),
> [PRECIOS.md](./PRECIOS.md), [DESPLIEGUE_DOKPLOY.md](./DESPLIEGUE_DOKPLOY.md).

Cada fase tiene **criterios de salida** verificables. Una fase no se cierra por fecha;
se cierra cuando sus criterios se cumplen en producción.

---

## Fase 1 — MVP: web + backend + infra (en construcción)

Todo lo definido en el contrato: API FastAPI, PostgreSQL, MediaMTX, frontend React,
Docker Compose desplegado con Dokploy. Aún sin app Android: la publicación se valida con
un cliente WHIP genérico (OBS 30+, GStreamer o `whip-client`) usando el `device_token`.

**Alcance**: auth (registro/login/JWT), planes seed y `/usage`, CRUD de dispositivos,
emparejamiento por código, comandos por REST→WS, canal WS de consola con estado en vivo,
auth hook de MediaMTX (publish/read/horas), tracker de sesiones (poll 30 s), dashboard
completo en español (lista, detalle con preview WHEP y controles, guía OBS, cuenta),
página pública de precios.

**Criterios de salida**
1. Desplegado en el VPS con Dokploy, TLS activo en `app.`, `api.` y `stream.${DOMAIN}`.
2. Flujo completo real: registrarse → crear dispositivo → emparejar (via `POST /pairing/claim`)
   → publicar WHIP con un cliente de prueba → ver el stream en OBS como Browser Source y
   en el preview del dashboard, con latencia < 1 s observada.
3. El auth hook rechaza: token inválido (publish), `view_token` inválido (read) y plan sin
   horas (publish) — probado con casos reales, no solo tests.
4. `stream_sessions` registra sesiones con precisión de ±1 min y `/usage` refleja las horas
   del mes en el dashboard.
5. Comando enviado desde el dashboard llega por WS a un cliente device simulado y el `ack`
   actualiza la consola en vivo.
6. Suite de tests del backend en verde y reinicio del VPS sin intervención manual
   (contenedores con restart y migraciones idempotentes).

---

## Fase 2 — App Android (6–8 semanas)

Especificación completa: [ANDROID_APP_SPEC.md](./ANDROID_APP_SPEC.md). Kotlin + CameraX +
libwebrtc, foreground service `camera`, transmisión con pantalla bloqueada, telemetría y
comandos, gestión térmica y de batería, guías por OEM.

Hitos internos sugeridos: (1) publicar WHIP con preview, (2) foreground service estable +
pantalla bloqueada, (3) WS de comandos completo, (4) adaptativo + térmica, (5) hardening
por OEM + Play Store.

**Criterios de salida**
1. Los 6 criterios de aceptación de la spec (§8) cumplidos, incluyendo 60 min con pantalla
   bloqueada en Pixel y Samsung de gama media.
2. Publicada en Google Play (producción o al menos open testing) con la declaración de
   foreground service `camera` aprobada.
3. 20+ dispositivos reales distintos en la beta con cupo (ver PRECIOS.md §5) transmitiendo
   sin intervención del equipo.
4. Tasa de reconexión automática > 95 % en cortes de red < 60 s (medida con telemetría).

---

## Fase 3 — Pagos y límites automáticos

MercadoPago + Stripe (y cripto como opción, ver PRECIOS.md §4): suscripciones mensual y
anual (−20 %), precio de fundador, webhooks → estado de suscripción propio en DB,
upgrade/downgrade en caliente, recordatorios de horas (80 % / 100 %), corte automático ya
existente vía auth hook, facturas/recibos por email.

**Criterios de salida**
1. Un usuario paga con tarjeta local vía MercadoPago y con tarjeta internacional vía
   Stripe; su plan cambia sin intervención manual y `/usage` refleja los nuevos límites.
2. Fallo de pago → reintentos y downgrade a Gratis al agotar el período, comunicado por
   email; nunca corte silencioso a mitad de stream.
3. Webhooks idempotentes (reenvíos de la pasarela no duplican estado) y conciliación
   básica: lo que dice la pasarela == lo que dice la DB, verificado por job diario.
4. Primeros 50 clientes pagos sin ticket de soporte de facturación irresoluble.

---

## Fase 4 — App iOS

El mercado iOS en LATAM es menor en volumen pero mayor en disposición a pagar. Swift +
ReplayKit no aplica (es cámara, no pantalla): AVFoundation + WebRTC.framework, mismo
contrato (pairing, WHIP, WS). Restricción honesta a investigar a fondo: iOS suspende el
acceso a cámara en background de forma más agresiva que Android; el modo realista puede
ser "pantalla encendida con brillo mínimo" u "solo audio en background". Se especificará
en un `IOS_APP_SPEC.md` propio al inicio de la fase.

**Criterios de salida**
1. Paridad de contrato: pairing, publicación WHIP, comandos y telemetría idénticos al
   dashboard (el backend no distingue plataforma salvo el campo `platform`).
2. Publicada en App Store con las limitaciones de background documentadas en la app y en
   la guía.
3. Sesión de 60 min estable en las condiciones que iOS permita, documentadas sin
   sobrepromesas.

---

## Fase 5 — Features pro

En orden tentativo de valor/esfuerzo:

1. **TURN server (coturn)** con TLS :443 para redes restrictivas (CGNAT, WiFi corporativo)
   — es infraestructura, no feature visible, pero destraba usuarios que hoy no conectan.
2. **Multi-cámara real**: vista en mosaico en el dashboard, límites por plan ya previstos
   (Pro 2, Estudio 4).
3. **Audio del celular como micrófono**: el track de audio ya viaja por WebRTC; exponerlo
   como fuente separada en OBS (segundo Browser Source solo-audio).
4. **Overlays y escenas remotas**: composición ligera sobre el player (marcos, nombre,
   estado) sin transcodificar — se hace en el Browser Source con CSS/JS.
5. **Escalado multi-nodo / regiones** según demanda real (ARQUITECTURA.md §6).

**Criterios de salida** (por feature, regla general)
1. Cada feature detrás de su flag de plan, medida (adopción y efecto en churn) antes de
   darla por cerrada.
2. TURN en particular: tasa de conexión exitosa de publicación > 99 % medida sobre la
   telemetría de la beta.

---

## Qué NO está en el roadmap (a propósito)

- Transcodificación/ABR en servidor, grabación en la nube, RTMP de salida a plataformas:
  convierten un relay barato en un negocio de cómputo caro; solo con demanda pagada clara.
- Kubernetes/microservicios: Compose + nodos MediaMTX horizontales llegan muy lejos.
- Apps de escritorio: OBS ya es nuestro "cliente de escritorio".

# OneVideo Android — Instalación y prueba del APK

Guía para instalar la app en un celular real y validar el flujo completo contra el
servidor desplegado. El APK debug se genera en
`android/app/build/outputs/apk/debug/app-debug.apk`.

## 1. Instalar el APK

**Opción A — copiar el archivo:** pasa `app-debug.apk` al celular (cable, Drive, WhatsApp
a ti mismo). Al abrirlo, Android pedirá permitir «instalar apps desconocidas» para esa
app (Archivos/Chrome): actívalo solo para esta instalación.

**Opción B — adb (con el celular en modo desarrollador y depuración USB):**

```bash
adb install -r "android/app/build/outputs/apk/debug/app-debug.apk"
```

> El APK es debug y sin firmar para la Play Store: es para pruebas de la beta. Para
> distribuir de verdad harán falta firma de release y (si se publica en Play) revisión
> de la política de foreground service de cámara.

## 2. Emparejar

1. En el dashboard web → **Crear dispositivo** → aparece el código de 8 caracteres.
2. En la app: el campo *Servidor* ya viene con la URL de prueba
   (`http://onevideo-api-…traefik.me`). Escribe el código y toca **Emparejar**.
3. El dispositivo debe pasar a **En línea** en el dashboard en segundos.

## 3. Probar el flujo completo

1. En la app toca **Transmitir** (o desde el dashboard: **Encender cámara**). Concede
   cámara, micrófono y notificaciones la primera vez.
2. En el dashboard debe verse el preview en vivo y el estado «Transmitiendo», con
   telemetría (batería, temperatura, red) actualizándose cada pocos segundos.
3. Prueba los controles remotos: cambiar frontal/trasera, calidad, reiniciar stream.
4. **La prueba clave — pantalla bloqueada:** con la transmisión activa, bloquea el
   celular. El video debe seguir corriendo en el dashboard. Déjalo 10+ minutos y
   observa la temperatura en la telemetría.
5. En OBS: Fuente → Navegador → pega la «URL del player» del dashboard. El video del
   celular aparece como fuente, listo para Kick/Twitch.

## 4. Si el fabricante mata la transmisión (Xiaomi, Huawei, Oppo, realme…)

- En la app, toca **Ignorar optimización de batería** y acepta.
- En Xiaomi/MIUI además: Ajustes → Apps → OneVideo → *Sin restricciones* en batería, y
  bloquea la app en Recientes (candado) para que MIUI no la cierre.
- La referencia por marca está en <https://dontkillmyapp.com>.
- Si aun así se corta, el dashboard mostrará el dispositivo «Desconectado»: eso es el
  OEM matando el servicio, no un bug del stream — repórtalo con marca/modelo/versión.

## 5. Prueba de reinicio

1. Con la **transmisión activa**, reinicia el celular (apagar y encender también vale).
2. Al desbloquear el equipo debe aparecer la notificación **«El celular se reinició —
   Toca para reanudar la transmisión»** (si la cámara estaba apagada pero el equipo
   emparejado, el texto dice «Toca para dejar tu cámara lista de nuevo»).
3. **Un toque** en la notificación abre la app, arranca el servicio y, si estabas
   transmitiendo antes del reinicio, enciende la cámara automáticamente. El dashboard
   debe volver a mostrar «Transmitiendo» en segundos.
4. Si la notificación no aparece: revisa que el permiso de notificaciones esté
   concedido y que el canal «Avisos» no esté silenciado (Ajustes → Apps → OneVideo →
   Notificaciones).

> **Por qué no se reanuda solo, sin tocar nada:** Android (14 y 15) prohíbe que una
> app inicie por su cuenta, desde segundo plano o al arrancar el sistema, un servicio
> en primer plano que use la cámara o el micrófono; además, aunque arrancara, el
> sistema le negaría el acceso a la cámara por la regla de «uso mientras la app está
> en pantalla». Es una restricción de privacidad del sistema que aplica a todas las
> apps por igual (no un límite de OneVideo). El máximo permitido es exactamente lo
> que hace la app: avisarte con una notificación para que un solo toque lo deje todo
> como estaba.

## 6. Qué reportar de cada prueba

Modelo y Android, red (wifi/datos), minutos de transmisión continua con pantalla
bloqueada, temperatura máxima vista en telemetría, y si algún control remoto no
respondió. Con 5–10 equipos distintos (ideal: al menos un Xiaomi y un Samsung de gama
media) sabremos si la estrategia de foreground service aguanta la beta.

## Grabación en la nube y códecs (corregido en v1.2.0)

Las grabaciones se guardan en fMP4, que **no admite VP8**. Hasta la v1.1.0 la app
dejaba que la negociación WebRTC eligiera códec y algunos equipos transmitían en
VP8: el stream se veía bien en vivo, pero la grabación quedaba **solo con audio**
(video en negro). Desde la **v1.2.0** la app pone H264 primero en la negociación
(todo celular lo trae por hardware), con VP8/VP9 de respaldo. Si pruebas grabación,
usa v1.2.0 o superior; las grabaciones en negro hechas antes son archivos de solo
audio y pueden eliminarse desde el dashboard.

## Limitaciones conocidas de esta versión

- La **linterna** no funciona mientras se transmite (limitación técnica de esta
  versión: la cámara está en uso por el encoder). El dashboard recibirá el error.
- El servidor de prueba va por **HTTP** (dominios traefik.me): la app lo permite
  explícitamente (`usesCleartextTraffic`). Con dominio propio y HTTPS, ese flag se
  quita antes de cualquier distribución seria.
- Sin preview local en el celular (decisión deliberada: ahorra batería y calor; el
  encuadre se ve en el dashboard).

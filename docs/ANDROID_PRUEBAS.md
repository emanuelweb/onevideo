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

## 5. Qué reportar de cada prueba

Modelo y Android, red (wifi/datos), minutos de transmisión continua con pantalla
bloqueada, temperatura máxima vista en telemetría, y si algún control remoto no
respondió. Con 5–10 equipos distintos (ideal: al menos un Xiaomi y un Samsung de gama
media) sabremos si la estrategia de foreground service aguanta la beta.

## Limitaciones conocidas de esta versión

- La **linterna** no funciona mientras se transmite (limitación técnica de esta
  versión: la cámara está en uso por el encoder). El dashboard recibirá el error.
- El servidor de prueba va por **HTTP** (dominios traefik.me): la app lo permite
  explícitamente (`usesCleartextTraffic`). Con dominio propio y HTTPS, ese flag se
  quita antes de cualquier distribución seria.
- Sin preview local en el celular (decisión deliberada: ahorra batería y calor; el
  encuadre se ve en el dashboard).

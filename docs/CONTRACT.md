# OneVideo — Contrato Técnico (fuente de verdad)

> **OneVideo — "La app de vídeo del futuro"**
> Servicio cloud que convierte el celular Android en cámara de streaming profesional.
> El celular publica su cámara a la nube en segundo plano (incluso con pantalla bloqueada);
> el streamer la consume desde OBS (Kick, Twitch, YouTube) como Browser Source, y la
> controla remotamente desde el dashboard web (encender/apagar cámara, cambiar frontal/trasera,
> calidad, linterna) sin tocar el celular.

Este documento es el CONTRATO entre componentes. Todos los agentes/desarrolladores deben
seguirlo exactamente: nombres de endpoints, campos JSON, variables de entorno, puertos y
rutas de archivos. Identificadores de código en inglés; textos de UI y docs en español.

---

## 1. Arquitectura

```
[App Android (fase 2)] --WHIP/WebRTC--> [MediaMTX :8889]
        |                                    |  WHEP / página player
        | WebSocket (control)                v
        v                            [OBS Browser Source / Preview en dashboard]
[API FastAPI :8000] <---auth HTTP--- [MediaMTX]
        |
   [PostgreSQL :5432]
        ^
[Web React (nginx :80)] --REST/WS--> API
```

Servicios Docker Compose (nombres exactos): `api`, `web`, `mediamtx`, `db`.

- `api` — FastAPI + Uvicorn, puerto interno **8000**. Dominio público: `api.${DOMAIN}`.
- `web` — build de React servido por nginx, puerto interno **80**. Dominio: `app.${DOMAIN}`.
- `mediamtx` — imagen `bluenviron/mediamtx:latest`. HTTP WebRTC (WHIP/WHEP/player) puerto **8889**
  (dominio `stream.${DOMAIN}`), ICE UDP **8189** publicado en el host (`8189:8189/udp`),
  API interna **9997** (solo red interna, sin exponer).
- `db` — `postgres:16-alpine`, volumen `db-data`, solo red interna.

Volumen `recordings-data`: montado en `/recordings` (rw) en `mediamtx` (escribe los MP4
de grabación) y en `api` (lista, sirve y elimina esos archivos). Ver §Grabaciones.

## 2. Variables de entorno (`.env.example` en la raíz)

```
DOMAIN=onevideo.example.com
PUBLIC_IP=203.0.113.10            # IP pública del VPS (para ICE de WebRTC)
POSTGRES_USER=onevideo
POSTGRES_PASSWORD=cambiame
POSTGRES_DB=onevideo
DATABASE_URL=postgresql+psycopg://onevideo:cambiame@db:5432/onevideo
SECRET_KEY=cambiame-64-chars
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=https://app.onevideo.example.com
MEDIAMTX_API_URL=http://mediamtx:9997
MEDIAMTX_AUTH_SECRET=cambiame-secreto-interno   # secreto compartido MediaMTX -> API (hook interno de auth)
STREAM_PUBLIC_URL=https://stream.onevideo.example.com
RECORDINGS_DIR=/recordings        # directorio de grabaciones en el contenedor api (volumen recordings-data)
SUPERADMIN_EMAILS=                # correos (separados por comas) habilitados para el bootstrap de super-admin
SUPERADMIN_BOOTSTRAP_TOKEN=       # secreto que además hay que enviar en el bootstrap (vacío = autoservicio apagado)

VITE_API_URL=https://api.onevideo.example.com
VITE_STREAM_URL=https://stream.onevideo.example.com
```

El frontend recibe `VITE_API_URL` y `VITE_STREAM_URL` como **build args** en su Dockerfile.

## 3. Rutas de streaming

- Path en MediaMTX: `live/<device_uuid>` (uuid con guiones, lowercase).
- Publicación (celular): `POST {STREAM_PUBLIC_URL}/live/<device_uuid>/whip` con header
  `Authorization: Bearer <device_token>`.
- Lectura WHEP (dashboard y OBS): `{STREAM_PUBLIC_URL}/live/<device_uuid>/whep?token=<view_token>`.
- Página player para OBS Browser Source: `{STREAM_PUBLIC_URL}/live/<device_uuid>?token=<view_token>`
  (MediaMTX sirve su player integrado en esa ruta).

## 4. API REST — prefijo `/api/v1`

Autenticación de usuario: `Authorization: Bearer <jwt>`. Errores: JSON `{"detail": "mensaje en español"}` con status HTTP apropiado.

### Auth
| Método | Ruta | Body | Respuesta 200 |
|---|---|---|---|
| POST | `/auth/register` | `{email, password, name, bootstrap_token?}` | `{access_token, token_type:"bearer", user}` |
| POST | `/auth/login` | `{email, password, bootstrap_token?}` | igual que register |

`bootstrap_token` es opcional y solo interviene en el bootstrap del primer super-admin
(ver más abajo); la UI nunca lo envía.
| GET | `/auth/me` | — | `User` |

`User = {id, email, name, plan: PlanPublic, is_superadmin: bool, created_at}`

### Planes y uso
| GET | `/plans` | público | `[PlanPublic]` |
| GET | `/usage` | auth | `{period_start, period_end, hours_used, hours_limit, devices_used, devices_limit}` |

`PlanPublic = {code, name, price_usd_month, max_devices, max_resolution, max_fps, monthly_hours, max_recording_gb, features: [string]}`

### Dispositivos (auth)
| GET | `/devices` | — | `[Device]` |
| POST | `/devices` | `{name}` | `DeviceWithPairing` (crea device + pairing code; valida límite del plan) |
| GET | `/devices/{id}` | — | `Device` |
| PATCH | `/devices/{id}` | `{name?, settings?}` | `Device` |
| DELETE | `/devices/{id}` | — | 204 |
| POST | `/devices/{id}/pairing-code` | — | `{code, expires_at}` (regenera; invalida anterior) |
| POST | `/devices/{id}/commands` | `{type, payload?}` | `{delivered: bool, command_id}` |
| GET | `/devices/{id}/stream` | — | `StreamInfo` |
| POST | `/devices/{id}/view-token/rotate` | — | `StreamInfo` |

```
Device = {id, name, platform, model, status: "online"|"offline"|"streaming",
          camera_on, recording_on, last_seen_at, created_at,
          telemetry: {battery, temp_c, charging, network, bitrate_kbps, resolution, facing} | null,
          settings: {resolution, fps, bitrate_kbps, facing}}
DeviceWithPairing = Device + {pairing_code, pairing_expires_at}
StreamInfo = {whip_url, whep_url, player_url, view_token}
Command types: "camera_on" | "camera_off" | "switch_camera" | "set_quality" | "torch_on" | "torch_off" | "restart_stream"
  set_quality payload: {resolution: "720p"|"1080p", fps: 30|60, bitrate_kbps: int}
```

### Emparejamiento (sin auth de usuario — lo llama la app Android)
| POST | `/pairing/claim` | `{code, platform:"android", model}` | `{device_id, device_token, whip_url, ws_url}` |

`code`: 8 caracteres A-Z0-9, expira a los 15 min, un solo uso. `device_token`: opaco, 43 chars urlsafe, se guarda **hasheado** (sha256) en DB.

### Grabaciones (auth de usuario, salvo el download por token)

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| POST | `/devices/{id}/recording` | `{enabled: bool}` | `Device` |
| GET | `/devices/{id}/recordings` | — | `{items: [Recording], used_bytes: int, limit_bytes: int}` |
| POST | `/devices/{id}/recordings/{rid}/download-token` | — | `{url: str, expires_at: datetime}` |
| GET | `/devices/{id}/recordings/{rid}/download?token=` | SIN header auth | MP4 con soporte Range |
| DELETE | `/devices/{id}/recordings/{rid}` | — | 204 |

```
Recording = {id: str, filename: str, started_at: datetime|null, size_bytes: int, in_progress: bool}
```

Reglas:
- `POST /recording {enabled:true}` con `used_bytes >= limit_bytes` → **403**
  "Alcanzaste el almacenamiento de grabaciones de tu plan. Elimina grabaciones o mejora tu plan.".
  Persiste `devices.recording_on`, aplica el cambio en MediaMTX best-effort (si no responde,
  el reconciliador del tracker lo aplicará) y notifica consolas (`device_status` por hub).
- `rid` = filename en base64url **sin padding**. Al decodificar debe casar
  `^[0-9A-Za-z_\-\.]+\.mp4$` (sin `..` ni separadores) y el path final debe resolverse
  dentro de `<RECORDINGS_DIR>/live/<device_id>/` (`resolve()` + `relative_to`); si no
  cumple → **404** "Grabación no encontrada.".
- `started_at` se parsea del nombre de archivo `%Y-%m-%d_%H-%M-%S-%f` (UTC); si no parsea → `null`.
- `in_progress`: mtime del archivo hace menos de 30 s. `DELETE` de una grabación en curso →
  **409** "Esa grabación está en curso. Detén la grabación antes de eliminarla.".
- `used_bytes` suma los bytes de **todos** los dispositivos del usuario (el límite es por
  usuario/plan, no por device). `limit_bytes = plan.max_recording_gb * 1024**3`.
- `download-token`: JWT HS256 con `SECRET_KEY`, claims `{sub: user_id, scope: "recording",
  device_id, rid, exp: now+6h}`. `url` absoluta construida desde el request
  (respeta `X-Forwarded-Proto`/`Host`).
- Separación de scopes en ambos sentidos: el JWT de sesión lleva `scope: "session"` y
  `decode_access_token` rechaza cualquier otro scope, así que un token de descarga
  filtrado no sirve como bearer de sesión (y viceversa).
- El token viaja en el query string (el `<video>` del navegador no puede mandar
  headers), así que un filtro sobre el logger `uvicorn.access` (`app/main.py`)
  redacta el valor de `token=` antes de que la línea llegue a `docker logs`.
- `GET /download?token=`: valida firma, scope, exp, que `device_id`/`rid` del token calcen
  con la URL y que el device siga siendo del `sub`. Respuesta con `Accept-Ranges: bytes`,
  soporte de `Range: bytes=a-b` (206 con `Content-Range`; sin Range o Range no parseable →
  200 completo, RFC 7233; 416 solo para rangos bien formados fuera del archivo), Content-Type
  `video/mp4`, streaming async por chunks de 512 KB, `Content-Disposition: inline` con filename.
- Cuota en el reconciliador: usuario sobre su límite ⇒ `recording_on=false` en todos sus
  devices, se quitan los path configs de MediaMTX y se notifican las consolas.

**Mecanismo** — MediaMTX graba nativamente; el backend no toca los bytes de video:

- Config estática en `infra/mediamtx.yml`, bloque `pathDefaults`:
  `record: no` (default), `recordPath: /recordings/%path/%Y-%m-%d_%H-%M-%S-%f`,
  `recordFormat: fmp4`, `recordPartDuration: 1s`, `recordSegmentDuration: 1h`,
  `recordDeleteAfter: 0s` (¡el default de MediaMTX es `1d` y borraría solo!).
- Encendido/apagado por dispositivo en runtime vía la API de control (`MEDIAMTX_API_URL`, :9997):
  - Activar: `POST /v3/config/paths/add/live%2F<device_uuid>` body `{"record": true}`;
    si ya existe → `PATCH /v3/config/paths/patch/live%2F<device_uuid>` mismo body.
  - Desactivar: `DELETE /v3/config/paths/delete/live%2F<device_uuid>` (el path vuelve a
    caer en el regex catch-all, sin grabación).
  - El nombre del path va URL-encodeado en la URL (la barra como `%2F`).
- Los archivos quedan en `/recordings/live/<device_uuid>/<YYYY-MM-DD_HH-MM-SS-ffffff>.mp4`
  (volumen `recordings-data`, compartido entre `mediamtx` y `api`; env `RECORDINGS_DIR`).
- La config runtime de MediaMTX vive en memoria: la verdad es `devices.recording_on` y el
  loop del tracker (cada 30 s) **reconcilia**: agrega los path configs que falten y elimina
  los configs explícitos `live/*` cuyo device ya no graba o no existe. Fallos de red → log
  y reintento en el siguiente ciclo, nunca crash del loop.

> Verificado contra la doc oficial de MediaMTX (repo `bluenviron/mediamtx`, rama `main`,
> 2026-08): las claves `record`, `recordPath`, `recordFormat` (`fmp4` | `mpegts`),
> `recordPartDuration`, `recordSegmentDuration` y `recordDeleteAfter` (default **1d**;
> `0s` lo desactiva) existen con esos nombres exactos en `pathDefaults` del `mediamtx.yml`
> de referencia y en el schema `PathConf` de `api/openapi.yaml` (que además define
> `recordMaxPartSize`, default 50M — dejamos el default). Los endpoints confirmados en
> `api/openapi.yaml` son `POST /v3/config/paths/add/{name}`,
> `PATCH /v3/config/paths/patch/{name}`, `POST /v3/config/paths/replace/{name}`,
> `DELETE /v3/config/paths/delete/{name}`, `GET /v3/config/paths/get/{name}` y
> `GET /v3/config/paths/list`; add/patch/replace aceptan un body `PathConf` con todos los
> campos opcionales.

### Administración (auth + `is_superadmin`)

Todas responden **403** `{"detail": "Necesitas permisos de administrador."}` a un usuario normal.

| Método | Ruta | Body | Respuesta |
|---|---|---|---|
| GET | `/admin/stats` | — | `AdminStats` |
| GET | `/admin/users?search=&limit=50&offset=0` | — | `{total: int, items: [AdminUser]}` |
| GET | `/admin/users/{user_id}` | — | `AdminUser` |
| POST | `/admin/users/{user_id}/plan` | `{plan_code, expires_at?: datetime\|null, note?: str}` | `AdminUser` |
| PATCH | `/admin/users/{user_id}` | `{is_active?: bool, is_superadmin?: bool}` | `AdminUser` |
| DELETE | `/admin/users/{user_id}` | — | 204 |
| GET | `/admin/users/{user_id}/grants` | — | `[PlanGrantPublic]` |

```


> **Códecs grabables**: fMP4 admite H264/H265/VP9/AV1 y Opus/AAC, pero **no VP8**.
> Si un publicador negocia VP8, MediaMTX graba solo las pistas soportadas (p. ej.
> solo el audio) y registra `skipping track (VP8)`. Por eso la app Android (v1.2.0+)
> antepone H264 en sus preferencias de códec.AdminUser = {id, email, name, is_active, is_superadmin, created_at,
             plan: PlanPublic, plan_source, plan_expires_at,
             devices_count: int, hours_used_month: float}
AdminStats = {users_total, users_active, devices_total, devices_streaming,
              hours_this_month: float, users_by_plan: [{plan_code, plan_name, count}]}
PlanGrantPublic = {id, plan_code, plan_name, source, granted_by_email: str|null,
                   expires_at, note, created_at}
```

Reglas:
- `search` filtra por correo o nombre (parcial, case-insensitive); listado ordenado por
  `created_at` descendente; `limit` 1..200, `offset` >= 0.
- `POST /plan` escribe **siempre** una fila en `plan_grants` (`source='admin'`,
  `granted_by` = admin actual) y actualiza `plan_id`, `plan_source='admin'` y `plan_expires_at`
  (`expires_at` ausente/`null` = plan sin vencimiento).
- `plan_code` inexistente → **404** "Plan no encontrado."; `expires_at` en el pasado → **422**
  "La fecha de vencimiento debe ser futura."; usuario inexistente → **404** "Usuario no encontrado.".
- Anti-autobloqueo (**409**): el admin no puede quitarse `is_superadmin`
  ("No puedes quitarte a ti mismo los permisos de administrador."), ni desactivarse
  ("No puedes desactivar tu propia cuenta."), ni borrarse ("No puedes eliminar tu propia cuenta.").

- Los cambios de `is_superadmin`/`is_active` y el borrado de cuentas quedan en el log estructurado
  `onevideo.audit` (admin, cuenta afectada, campo, valor anterior y nuevo). Las asignaciones de
  plan siguen auditándose en la tabla `plan_grants`.
- Al bajar de plan (por admin o por vencimiento) se recorta también la calidad guardada en
  `devices.settings` y se envía `set_quality` a los dispositivos conectados: el enforcement de
  calidad es cooperativo, así que sin ese recorte el celular seguiría publicando en 1080p60.
- `PATCH is_active=false` y `DELETE` cierran los WebSocket vivos del usuario (igual que
  `DELETE /devices/{id}`), para no dejar un stream huérfano publicando.

**Bootstrap del primer super-admin**: hacen falta **dos** variables de entorno y un envío
explícito del secreto; el correo por sí solo no promueve a nadie.

1. `SUPERADMIN_EMAILS`: correos (separados por comas, case-insensitive) habilitados.
2. `SUPERADMIN_BOOTSTRAP_TOKEN`: secreto que hay que mandar en el campo opcional
   `bootstrap_token` del cuerpo de `/auth/register` o `/auth/login`. Vacío = autoservicio apagado.

```
curl -X POST https://api.${DOMAIN}/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jefa@ejemplo.com","password":"...","bootstrap_token":"<SUPERADMIN_BOOTSTRAP_TOKEN>"}'
```

Comparar solo la cadena de correo sería una escalada de privilegios: el correo del dueño suele ser
público, así que quien se adelantara a registrarlo quedaría como administrador con acceso total al
panel. El secreto solo lo conoce quien edita las variables del despliegue, que es justo quien debe
poder crear al primer administrador; la UI no lo pide en ningún formulario.

El bootstrap actúa **una sola vez por cuenta** (`users.superadmin_bootstrapped_at`): tanto la
promoción automática como cualquier cambio manual del rol (panel o CLI) cierran esa puerta, de modo
que **una revocación no se deshace sola en el siguiente inicio de sesión**.

Alternativa manual: `docker exec <contenedor-api> python scripts/manage.py promote correo@ejemplo.com`
(subcomandos `promote`, `demote`, `list-admins`).

### Interno (solo red Docker — lo llama MediaMTX)
| POST | `/internal/mediamtx/auth?secret=<MEDIAMTX_AUTH_SECRET>` | payload de MediaMTX | 200 si autorizado, 401 si no |

Payload que envía MediaMTX: `{user, password, token, ip, action, path, protocol, id, query}`.
Autenticación del llamante: como el prefijo `/api/v1` queda expuesto por el reverse proxy y la
IP de cliente vista por uvicorn (`X-Forwarded-For`) es falsificable, MediaMTX se autentica con
el secreto compartido `MEDIAMTX_AUTH_SECRET` en el query param `secret` de la URL del hook
(docker-compose lo inyecta vía `MTX_AUTHHTTPADDRESS`). Si `MEDIAMTX_AUTH_SECRET` está vacío
(dev/tests), el API exige en su lugar que la IP del cliente sea privada/loopback.
Reglas:
- `action == "publish"`: el bearer llega en `token` o `password` (MediaMTX pasa el header Authorization como user/password o token según cliente) → debe corresponder al `device_token` (sha256) del device cuyo uuid está en `path` (`live/<uuid>`), y el plan del dueño debe tener horas disponibles.
- `action == "read"`: extraer `token=` del campo `query` → debe coincidir con el `view_token` del device del path.
- `action == "api"` u otros orígenes internos: permitir (el secreto ya autenticó al llamante como interno); sin secreto configurado, permitir solo si `ip` es de la red interna. Nunca usar `ip` del payload como criterio cuando hay secreto: lo controla el llamante.

## 5. WebSockets

### Canal del dispositivo — `GET /api/v1/devices/ws?token=<device_token>`
Mensajes JSON `{type, payload}`.
- Device→Server: `status` → payload = telemetry (ver Device.telemetry) + `camera_on: bool`.
  El server actualiza `last_seen_at`, `status`, telemetría en memoria/DB y reenvía a las consolas del dueño.
- Server→Device: `command` → `{command_id, type, payload}`.
- Device→Server: `ack` → `{command_id, ok, error?}`.
Al conectar: server marca device `online`; al desconectar: `offline` y notifica consolas.

### Canal de consola (dashboard) — `GET /api/v1/console/ws?token=<jwt>`
- Server→Console: `device_status` → `{device: Device}` (push en cada cambio).
- Console no envía comandos por WS (usa REST `/devices/{id}/commands`).

## 6. Base de datos (PostgreSQL, SQLAlchemy 2 + Alembic)

```
plans:            id PK, code UNIQUE, name, price_usd_month NUMERIC(6,2), max_devices INT,
                  max_resolution TEXT, max_fps INT, monthly_hours INT NULL (NULL = ilimitado),
                  max_recording_gb INT NOT NULL DEFAULT 1, features JSONB, sort_order INT
users:            id UUID PK, email UNIQUE (citext o lower-index), password_hash, name,
                  plan_id FK->plans, plan_source TEXT NOT NULL DEFAULT 'signup',
                  plan_expires_at TIMESTAMPTZ NULL, is_active BOOL,
                  is_superadmin BOOL NOT NULL DEFAULT false,
                  superadmin_bootstrapped_at TIMESTAMPTZ NULL, created_at
plan_grants:      id BIGSERIAL PK, user_id FK->users ON DELETE CASCADE (index),
                  plan_id FK->plans, granted_by FK->users ON DELETE SET NULL NULL,
                  source TEXT NOT NULL, expires_at TIMESTAMPTZ NULL, note TEXT NULL, created_at
devices:          id UUID PK, user_id FK, name, platform, model, device_token_hash TEXT NULL,
                  view_token TEXT, camera_on BOOL, recording_on BOOL NOT NULL DEFAULT false,
                  status TEXT, last_seen_at, settings JSONB, created_at
pairing_codes:    code PK, device_id FK, expires_at, used_at NULL
stream_sessions:  id PK, device_id FK, started_at, ended_at NULL
```

Seed de planes (migración o startup):
| code | name | USD/mes | devices | res | fps | horas/mes | grabación (GB) |
|---|---|---|---|---|---|---|---|
| free | Gratis | 0 | 1 | 720p | 30 | 15 | 1 |
| creator | Creador | 4.99 | 1 | 1080p | 30 | 60 | 5 |
| pro | Pro | 9.99 | 2 | 1080p | 60 | 150 | 20 |
| studio | Estudio | 19.99 | 4 | 1080p | 60 | NULL (fair use) | 40 |

El seed añade además a `plans.features` la línea "X GB de grabaciones en la nube" por plan.

Horas usadas del período = suma de duración de `stream_sessions` del mes calendario en curso.
Un tracker en el `api` consulta `GET {MEDIAMTX_API_URL}/v3/paths/list` cada 30 s: paths activos
con `source != null` ⇒ sesión abierta; abre/cierra `stream_sessions` según corresponda.

## 7. Stack y layout de archivos

```
/ (raíz del repo)
  docker-compose.yml, .env.example, README.md, .gitignore, .dockerignore
  backend/   Dockerfile, requirements.txt, alembic.ini, alembic/, app/, scripts/, tests/
    scripts/manage.py  (CLI: promote / demote / list-admins)
    app/main.py, config.py, db.py, security.py, deps.py
    app/models/*.py  app/schemas/*.py  app/api/v1/*.py  app/services/*.py
  frontend/  Dockerfile, nginx.conf, package.json, vite.config.ts, index.html, src/
  infra/     mediamtx.yml
  docs/      CONTRACT.md (este), ARQUITECTURA.md, DESPLIEGUE_DOKPLOY.md,
             ANDROID_APP_SPEC.md, PRECIOS.md, ROADMAP.md
```

**Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (sync + psycopg), Alembic, PyJWT, bcrypt
(directo, sin passlib), httpx, pydantic-settings. Sin Celery ni Redis en el MVP (el tracker
corre como tarea asyncio dentro del api). Tests: pytest con SQLite in-memory para lo que no
requiera Postgres.

**Frontend**: Vite + React 18 + TypeScript + react-router-dom. **Sin framework CSS**: un
`src/styles.css` con variables CSS, tema oscuro moderno (violeta/cian como acentos, apto para
streamers). Cliente WHEP propio (~60 líneas: RTCPeerConnection + POST SDP). Fetch wrapper
propio, sin axios ni react-query. UI 100 % en español.

Páginas: `/login`, `/registro`, `/precios` (pública), `/app` (dashboard con lista de
dispositivos + estado en vivo vía WS), `/app/dispositivos/:id` (preview WHEP en vivo +
controles: cámara on/off, frontal/trasera, calidad, linterna, URLs para OBS con botón
copiar), `/app/guia-obs` (guía paso a paso OBS/Kick/Twitch), `/app/cuenta` (plan y uso).

## 8. Reglas transversales

- Enforcement de calidad (res/fps) es **cooperativo**: el server manda `set_quality` según el
  plan; el server no transcodifica (MVP). Documentarlo donde aplique.
- Los tokens de dispositivo y view tokens se generan con `secrets.token_urlsafe(32)`.
- El límite de horas se aplica en el auth hook de publish (si excedido → 401) y se muestra en `/usage`.
- **El plan activo es dato propio del usuario** (`plan_id` + `plan_source` + `plan_expires_at`): la
  lógica de límites nunca depende de quién lo otorgó. Hoy lo escribe `/admin`; mañana un webhook de
  Stripe/MercadoPago escribirá el mismo estado con `plan_source='stripe'|'mercadopago'`. Antes de
  conectar el primer webhook hay que darle a `plan_grants` una clave de idempotencia
  (`external_id` + `UNIQUE(source, external_id)`): ver ROADMAP §Fase 3.
- **Vencimiento con degradación perezosa**: `services.plans.resolve_effective_plan(db, user)` baja al
  plan `free` (con `plan_source='signup'`, `plan_expires_at=NULL`) cuando la fecha ya pasó. Se invoca
  en `deps.get_current_user()` (toda la API autenticada) y en el hook `action == "publish"` de
  `/internal/mediamtx/auth` (publicación del celular). El resto del código usa `user.plan` sin cambios.
- Passwords con bcrypt (cost 12). JWT de sesión HS256 con `SECRET_KEY`, claims `sub` = user id
  y `scope: "session"` (obligatorio: la API rechaza JWT con otro scope, p. ej. los de descarga
  de grabaciones).
- CORS: solo `CORS_ORIGINS`.
- Todo texto visible para usuarios finales: español neutro LATAM.

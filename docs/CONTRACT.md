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
| POST | `/auth/register` | `{email, password, name}` | `{access_token, token_type:"bearer", user}` |
| POST | `/auth/login` | `{email, password}` | igual que register |
| GET | `/auth/me` | — | `User` |

`User = {id, email, name, plan: PlanPublic, created_at}`

### Planes y uso
| GET | `/plans` | público | `[PlanPublic]` |
| GET | `/usage` | auth | `{period_start, period_end, hours_used, hours_limit, devices_used, devices_limit}` |

`PlanPublic = {code, name, price_usd_month, max_devices, max_resolution, max_fps, monthly_hours, features: [string]}`

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
          camera_on, last_seen_at, created_at,
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
                  features JSONB, sort_order INT
users:            id UUID PK, email UNIQUE (citext o lower-index), password_hash, name,
                  plan_id FK->plans, is_active BOOL, created_at
devices:          id UUID PK, user_id FK, name, platform, model, device_token_hash TEXT NULL,
                  view_token TEXT, camera_on BOOL, status TEXT, last_seen_at, settings JSONB, created_at
pairing_codes:    code PK, device_id FK, expires_at, used_at NULL
stream_sessions:  id PK, device_id FK, started_at, ended_at NULL
```

Seed de planes (migración o startup):
| code | name | USD/mes | devices | res | fps | horas/mes |
|---|---|---|---|---|---|---|
| free | Gratis | 0 | 1 | 720p | 30 | 15 |
| creator | Creador | 4.99 | 1 | 1080p | 30 | 60 |
| pro | Pro | 9.99 | 2 | 1080p | 60 | 150 |
| studio | Estudio | 19.99 | 4 | 1080p | 60 | NULL (fair use) |

Horas usadas del período = suma de duración de `stream_sessions` del mes calendario en curso.
Un tracker en el `api` consulta `GET {MEDIAMTX_API_URL}/v3/paths/list` cada 30 s: paths activos
con `source != null` ⇒ sesión abierta; abre/cierra `stream_sessions` según corresponda.

## 7. Stack y layout de archivos

```
/ (raíz del repo)
  docker-compose.yml, .env.example, README.md, .gitignore, .dockerignore
  backend/   Dockerfile, requirements.txt, alembic.ini, alembic/, app/, tests/
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
- Passwords con bcrypt (cost 12). JWT HS256 con `SECRET_KEY`, claim `sub` = user id.
- CORS: solo `CORS_ORIGINS`.
- Todo texto visible para usuarios finales: español neutro LATAM.

# OneVideo — La app de vídeo del futuro

OneVideo es un servicio cloud que convierte tu celular Android en una cámara de streaming
profesional. El celular publica su cámara a la nube en segundo plano (incluso con la
pantalla bloqueada), y el streamer la consume desde OBS (Kick, Twitch, YouTube) como
Browser Source, controlándola remotamente desde el dashboard web: encender/apagar cámara,
cambiar frontal/trasera, calidad y linterna, sin tocar el celular.

## Arquitectura

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

Cuatro servicios en Docker Compose:

| Servicio   | Rol                                            | Dominio público          |
|------------|------------------------------------------------|--------------------------|
| `api`      | FastAPI + Uvicorn (REST, WebSockets, auth)     | `api.${DOMAIN}`          |
| `web`      | Dashboard React servido por nginx              | `app.${DOMAIN}`          |
| `mediamtx` | Servidor de medios WebRTC (WHIP/WHEP/player)   | `stream.${DOMAIN}`       |
| `db`       | PostgreSQL 16                                  | — (solo red interna)     |

El único puerto de medios publicado al host es **8189/udp** (ICE de WebRTC). El resto del
tráfico entra por el reverse proxy con HTTPS.

## Estructura del repo

```
docker-compose.yml   Orquestación de los 4 servicios
.env.example         Variables de entorno (copiar a .env)
backend/             API FastAPI (Python 3.12, SQLAlchemy 2, Alembic)
frontend/            Dashboard Vite + React 18 + TypeScript
infra/mediamtx.yml   Configuración de MediaMTX (solo WebRTC en el MVP)
docs/                Contrato técnico y guías
```

## Quickstart local

Requisitos: Docker y Docker Compose v2.

```bash
cp .env.example .env
# Edita .env si lo necesitas (para uso local los valores por defecto sirven)

# Red compartida con Traefik. En el VPS ya existe (la crea Dokploy);
# en tu máquina hay que crearla una sola vez:
docker network create dokploy-network

docker compose up -d --build
```

Por seguridad, `docker-compose.yml` no publica los puertos de `web`, `api` ni `mediamtx`
al host (en producción entra todo por el reverse proxy). Para acceder desde tu máquina en
desarrollo, crea un `docker-compose.override.yml` (ignorado por git) con:

```yaml
services:
  web:
    ports:
      - "8080:80"
  api:
    ports:
      - "8000:8000"
  mediamtx:
    ports:
      - "8889:8889"
```

y vuelve a levantar con `docker compose up -d`. Luego:

- Dashboard: <http://localhost:8080>
- API: <http://localhost:8000/api/v1/plans>
- Streaming (WHIP/WHEP/player): <http://localhost:8889>

Verificación rápida:

```bash
curl http://localhost:8000/api/v1/plans
```

## Documentación

- [docs/CONTRACT.md](docs/CONTRACT.md) — **Contrato técnico (fuente de verdad)**: endpoints,
  esquemas JSON, variables de entorno, puertos y layout de archivos.
- [docs/DESPLIEGUE_DOKPLOY.md](docs/DESPLIEGUE_DOKPLOY.md) — Guía de despliegue en un VPS
  con Dokploy (Hostinger, Ubuntu 24.04).
- [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) — Decisiones de diseño y por qué WebRTC.
- [docs/ANDROID_APP_SPEC.md](docs/ANDROID_APP_SPEC.md) — Especificación de la app Android (fase 2),
  incluida la captura con pantalla bloqueada y la gestión térmica.
- [docs/PRECIOS.md](docs/PRECIOS.md) — Planes, economía unitaria y estrategia de cobro en LATAM.
- [docs/ROADMAP.md](docs/ROADMAP.md) — Fases del producto con criterios de salida.

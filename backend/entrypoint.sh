#!/bin/sh
# Aplica migraciones (reintenta hasta que la DB esté disponible) y arranca la API.
set -e

tries=0
until alembic upgrade head; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    echo "No se pudieron aplicar las migraciones: base de datos no disponible." >&2
    exit 1
  fi
  echo "Base de datos no disponible; reintentando en 2 s..."
  sleep 2
done

# Un solo worker: el hub de WebSockets y el tracker de uso viven en memoria del proceso.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"

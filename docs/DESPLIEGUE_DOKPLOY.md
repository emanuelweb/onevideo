# Despliegue de OneVideo en un VPS con Dokploy

Guía paso a paso para desplegar OneVideo en un VPS de Hostinger con Ubuntu 24.04,
usando [Dokploy](https://dokploy.com) como panel de despliegue (Docker + Traefik +
Let's Encrypt automáticos).

## 1. Requisitos del VPS

- **Plan recomendado: Hostinger KVM 2** — 2 vCPU, 8 GB RAM, 100 GB NVMe. Es suficiente
  para el MVP (MediaMTX no transcodifica: solo reenvía el vídeo, el consumo de CPU por
  stream es bajo). El mínimo absoluto para Dokploy es 2 GB de RAM y 30 GB de disco, pero
  con 8 GB los builds de Docker y varios streams simultáneos van holgados.
- **SO: Ubuntu 24.04 LTS** (imagen limpia, sin panel preinstalado).
- Acceso SSH como root (o usuario con sudo).
- Un dominio propio (ejemplo en esta guía: `onevideo.example.com`).

## 2. Instalar Dokploy

Conéctate por SSH y ejecuta:

```bash
ssh root@TU_IP_PUBLICA
apt update && apt upgrade -y
curl -sSL https://dokploy.com/install.sh | sh
```

El script instala Docker, Traefik y el panel de Dokploy. Al terminar, abre
`http://TU_IP_PUBLICA:3000` en el navegador y crea la cuenta de administrador.

> Dokploy necesita libres los puertos **80** y **443** (Traefik) y **3000** (panel).
> No instales nginx/apache en el host.

## 3. DNS

En tu proveedor de DNS crea tres registros **A** apuntando a la IP pública del VPS:

| Tipo | Nombre                      | Valor           |
|------|-----------------------------|-----------------|
| A    | `app.onevideo.example.com`  | `TU_IP_PUBLICA` |
| A    | `api.onevideo.example.com`  | `TU_IP_PUBLICA` |
| A    | `stream.onevideo.example.com` | `TU_IP_PUBLICA` |

Espera a que propaguen (verifica con `dig +short app.onevideo.example.com`). Let's Encrypt
no podrá emitir certificados hasta que los registros resuelvan a la IP del VPS.

## 4. Firewall (UFW + panel de Hostinger)

En el VPS:

```bash
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP (Traefik / retos ACME)
ufw allow 443/tcp     # HTTPS (Traefik)
ufw allow 3000/tcp    # Panel Dokploy (ciérralo cuando termines la configuración)
ufw allow 8189/udp    # ICE UDP de WebRTC (imprescindible para el vídeo)
ufw enable
```

> Nota: Docker publica sus puertos con reglas iptables propias que pueden saltarse UFW,
> pero mantener UFW coherente documenta la intención y protege los servicios del host.

Si tu VPS de Hostinger usa el **firewall del panel (hPanel → VPS → Firewall)**, replica
las mismas reglas ahí: TCP 22, 80, 443, 3000 y **UDP 8189**. Si UDP 8189 está cerrado, el
handshake WebRTC (WHIP/WHEP) fallará aunque el resto del sitio funcione.

Cuando todo esté configurado, puedes cerrar el 3000 (`ufw delete allow 3000/tcp`) y
acceder al panel por túnel SSH: `ssh -L 3000:localhost:3000 root@TU_IP_PUBLICA`.

## 5. Crear el proyecto Compose en Dokploy

1. En el panel: **Create Project** → nómbralo `onevideo`.
2. Dentro del proyecto: **Create Service → Compose**.
3. En **Provider**, conecta tu repositorio Git (GitHub/GitLab o URL de git genérica),
   rama `main`.
4. **Compose Path**: `./docker-compose.yml` (raíz del repo).
5. Todavía **no** despliegues: primero configura variables y dominios (pasos 6 y 7).

## 6. Variables de entorno

En la pestaña **Environment** del servicio Compose, pega el contenido de `.env.example`
ajustado con valores reales:

```env
DOMAIN=onevideo.example.com
PUBLIC_IP=TU_IP_PUBLICA
POSTGRES_USER=onevideo
POSTGRES_PASSWORD=<contraseña fuerte>
POSTGRES_DB=onevideo
DATABASE_URL=postgresql+psycopg://onevideo:<contraseña fuerte>@db:5432/onevideo
SECRET_KEY=<64 caracteres aleatorios>
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=https://app.onevideo.example.com
MEDIAMTX_API_URL=http://mediamtx:9997
MEDIAMTX_AUTH_SECRET=<32 caracteres aleatorios>
STREAM_PUBLIC_URL=https://stream.onevideo.example.com
SUPERADMIN_EMAILS=tu-correo@ejemplo.com
SUPERADMIN_BOOTSTRAP_TOKEN=<32 caracteres aleatorios>
VITE_API_URL=https://api.onevideo.example.com
VITE_STREAM_URL=https://stream.onevideo.example.com
```

Consejos:

- Genera secretos en el VPS: `openssl rand -hex 32` (para `SECRET_KEY`) y
  `openssl rand -base64 24` (para `POSTGRES_PASSWORD`; recuerda reflejarla también en
  `DATABASE_URL`).
- `MEDIAMTX_AUTH_SECRET` (genéralo con `openssl rand -hex 16`) es el secreto compartido con
  el que MediaMTX se identifica ante el API al validar cada publish/read. **No lo dejes
  vacío en producción**: sin él, el hook `/internal/mediamtx/auth` cae al modo de desarrollo
  y solo verifica que la IP del cliente sea privada, un criterio falsificable a través del
  reverse proxy.
- `SUPERADMIN_EMAILS` + `SUPERADMIN_BOOTSTRAP_TOKEN` crean al primer administrador sin entrar
  al contenedor. Hacen falta las dos: el correo habilita la cuenta y el secreto
  (`openssl rand -hex 16`) prueba que quien pide el rol es quien configura el despliegue.
  Con el token vacío el autoservicio queda apagado. Una vez desplegado, basta con un
  inicio de sesión que incluya el secreto:

  ```bash
  curl -X POST https://api.onevideo.example.com/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"tu-correo@ejemplo.com","password":"tu-contraseña","bootstrap_token":"<token>"}'
  ```

  Después conviene vaciar ambas variables. Alternativa con acceso al contenedor:
  `docker exec <contenedor-api> python scripts/manage.py promote tu-correo@ejemplo.com`.
  El rol se decide una sola vez por cuenta: si más adelante lo quitas desde el panel, la
  variable de entorno ya no vuelve a otorgarlo.
- `PUBLIC_IP` es crítica: MediaMTX la anuncia en los candidatos ICE
  (`MTX_WEBRTCADDITIONALHOSTS`). Si está mal, el WebRTC conecta la señalización pero
  nunca llega el vídeo.
- `VITE_API_URL` y `VITE_STREAM_URL` son **build args** del frontend: si las cambias,
  necesitas redesplegar (rebuild) para que el dashboard las tome.

## 7. Dominios por servicio (HTTPS con Let's Encrypt)

En la pestaña **Domains** del servicio Compose agrega tres dominios:

| Host                          | Service Name | Container Port | HTTPS | Certificate   |
|-------------------------------|--------------|----------------|-------|---------------|
| `app.onevideo.example.com`    | `web`        | `80`           | Sí    | Let's Encrypt |
| `api.onevideo.example.com`    | `api`        | `8000`         | Sí    | Let's Encrypt |
| `stream.onevideo.example.com` | `mediamtx`   | `8889`         | Sí    | Let's Encrypt |

Notas:

- El "Container Port" es solo para el enrutado interno de Traefik; no expone el puerto
  a internet.
- Con Docker Compose, Dokploy **no recarga dominios en caliente**: tras agregar o cambiar
  dominios hay que redesplegar.
- El puerto **8189/udp no pasa por Traefik**: lo publica Docker directamente al host
  (así está declarado en `docker-compose.yml`); por eso se abre en el firewall.

## 8. Desplegar

Pulsa **Deploy**. Dokploy clona el repo, construye `backend/` y `frontend/` (con los
build args `VITE_*`) y levanta los cuatro servicios. Sigue el progreso en la pestaña
**Logs**; el primer build tarda varios minutos.

## 9. Verificación post-deploy

### 9.1 API y web

```bash
curl https://api.onevideo.example.com/api/v1/plans
# → JSON con los planes (free, creator, pro, studio)
```

Abre `https://app.onevideo.example.com`, regístrate y crea un dispositivo desde el
dashboard: obtendrás un código de emparejamiento.

### 9.2 Publicar un stream de prueba (sin celular)

Simula la app Android reclamando el código de emparejamiento:

```bash
curl -X POST https://api.onevideo.example.com/api/v1/pairing/claim \
  -H "Content-Type: application/json" \
  -d '{"code":"CODIGO8C","platform":"android","model":"prueba-gstreamer"}'
# → {"device_id":"<uuid>","device_token":"<token>","whip_url":"...","ws_url":"..."}
```

**Opción A — OBS Studio (v30+):** en OBS crea un perfil de prueba,
`Ajustes → Emisión`:

- Servicio: **WHIP**
- Servidor: `https://stream.onevideo.example.com/live/<device_id>/whip`
- Token de portador (Bearer): `<device_token>`

Pulsa "Iniciar transmisión".

**Opción B — GStreamer (con gst-plugins-rs):**

```bash
gst-launch-1.0 videotestsrc is-live=true ! videoconvert ! \
  x264enc tune=zerolatency bitrate=2000 ! rtph264pay ! \
  whipclientsink signaller::whip-endpoint="https://stream.onevideo.example.com/live/<device_id>/whip" \
                 signaller::auth-token="<device_token>"
```

### 9.3 Ver el stream

En el dashboard (`/app/dispositivos/<id>`) debe verse el preview WHEP en vivo. También
puedes abrir el player integrado de MediaMTX (el que se usa como Browser Source en OBS):

```
https://stream.onevideo.example.com/live/<device_id>?token=<view_token>
```

El `view_token` aparece en el dashboard (sección URLs para OBS) o vía
`GET /api/v1/devices/<id>/stream`.

Si la señalización conecta pero no aparece el vídeo, revisa: `PUBLIC_IP` en `.env` y
UDP 8189 abierto en UFW **y** en el firewall de Hostinger.

## 10. Backups de PostgreSQL

Crea el script en el VPS:

```bash
mkdir -p /opt/onevideo
cat > /opt/onevideo/backup-db.sh <<'EOF'
#!/usr/bin/env bash
# Backup diario de la base de datos de OneVideo (retiene 14 días)
set -euo pipefail
BACKUP_DIR=/opt/onevideo/backups
mkdir -p "$BACKUP_DIR"
CONTAINER=$(docker ps --filter "name=db" --format '{{.Names}}' | grep -m1 db)
docker exec "$CONTAINER" pg_dump -U onevideo -d onevideo \
  | gzip > "$BACKUP_DIR/onevideo-$(date +%F-%H%M).sql.gz"
find "$BACKUP_DIR" -name 'onevideo-*.sql.gz' -mtime +14 -delete
EOF
chmod +x /opt/onevideo/backup-db.sh
```

Prográmalo con cron (diario a las 03:00):

```bash
crontab -e
# agrega:
0 3 * * * /opt/onevideo/backup-db.sh >> /var/log/onevideo-backup.log 2>&1
```

Restaurar un backup:

```bash
gunzip -c /opt/onevideo/backups/onevideo-2026-08-17-0300.sql.gz \
  | docker exec -i $(docker ps --filter "name=db" --format '{{.Names}}' | grep -m1 db) \
    psql -U onevideo -d onevideo
```

> Alternativa: Dokploy también ofrece backups programados a S3 compatibles desde el panel
> (pestaña Backups), útil si prefieres copias fuera del VPS.

## 11. Actualizaciones

Flujo normal: haz `git push` a `main` y en Dokploy pulsa **Deploy** (o activa
**Auto Deploy** en la configuración del servicio para que cada push despliegue solo,
vía webhook del proveedor Git). Dokploy reconstruye solo lo que cambió y reinicia los
servicios; el volumen `db-data` conserva los datos entre despliegues.

> **Cuidado con `infra/mediamtx.yml`.** Ese archivo entra al contenedor como bind mount,
> no como parte de la imagen. Si lo editas, `docker compose up` no ve ningún cambio en la
> *definición* del servicio y **no recrea el contenedor**: MediaMTX sigue corriendo con la
> configuración que leyó al arrancar, y el despliegue parece exitoso sin haber aplicado
> nada. Después de tocar ese archivo hay que reiniciar el contenedor `mediamtx`
> explícitamente (botón *Restart* en Dokploy, o `docker restart <contenedor>`).

## 11.1 Despliegue temporal con dominios de Traefik

Para probar sin dominio propio, Dokploy genera hosts del tipo
`<nombre>-<hash>-<ip-con-guiones>.traefik.me`, que resuelven solos a la IP del VPS.

Van en **HTTP, no HTTPS**, y es a propósito: `traefik.me` no está en la Public Suffix
List, así que Let's Encrypt lo trata como un único dominio registrado y su límite de 50
certificados por semana lo comparten todos los usuarios de Dokploy del mundo. Pedir un
certificado ahí falla. Mientras uses traefik.me, deja los tres dominios en HTTP para que
no haya *mixed content* entre el dashboard, el API y el stream.

Esto sirve para validar el stack, pero tiene dos límites que obligan a un dominio propio
antes de la fase 2:

- **La app Android bloquea tráfico en claro** por defecto (`cleartextTrafficPermitted`),
  así que no podrá publicar contra un endpoint HTTP.
- Sin HTTPS no hay contexto seguro en el navegador para funciones futuras de captura.

Cuando tengas el dominio real: cambia los tres hosts en la pestaña **Domains** a
`app/api/stream.tudominio.com` con `certificateType: letsencrypt` y `https: true`,
actualiza `CORS_ORIGINS`, `STREAM_PUBLIC_URL`, `VITE_API_URL` y `VITE_STREAM_URL` a
`https://`, y **redespliega** (las `VITE_*` son build args: sin rebuild el dashboard
seguiría apuntando a las URLs viejas).

## 12. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| Certificado no se emite | DNS aún no propaga o puerto 80 cerrado | Verifica `dig`, UFW y firewall de Hostinger |
| `502 Bad Gateway` | Servicio aún arrancando o caído | Revisa Logs del servicio en Dokploy |
| WHIP devuelve `401` | `device_token` inválido o límite de horas del plan agotado | Regenera emparejamiento; revisa `/api/v1/usage` |
| Señalización OK pero sin vídeo | `PUBLIC_IP` incorrecta o UDP 8189 cerrado | Corrige `.env` y firewall; redespliega |
| WHIP crea la sesión y luego da `Connection refused` | MediaMTX está anunciando IPs privadas de Docker como candidatos ICE | Verifica `webrtcIPsFromInterfaces: no` en `infra/mediamtx.yml`; los clientes simples solo prueban el primer candidato |
| Frontend apunta a URLs viejas | Cambiaste `VITE_*` sin rebuild | Redespliega (son build args) |

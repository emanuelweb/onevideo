"""Tracker de uso: sincroniza stream_sessions con los paths activos de MediaMTX.

Cada 30 s consulta GET {MEDIAMTX_API_URL}/v3/paths/list; un path `live/<uuid>`
con `source != null` implica una publicación activa. Abre/cierra stream_sessions
según corresponda y notifica los cambios de estado a las consolas conectadas.

En el mismo ciclo reconcilia la grabación en la nube: la config runtime de
MediaMTX vive en memoria (se pierde si su contenedor se reinicia), así que la
verdad es `devices.recording_on`. Se agregan los path configs que falten, se
eliminan los configs explícitos `live/*` huérfanos y se aplica la cuota de
almacenamiento por usuario (sobre cuota → grabación apagada en sus devices).
"""
import asyncio
import logging
import uuid

import httpx
from sqlalchemy import select

from app import db as database
from app.config import settings
from app.models import Device, StreamSession, User
from app.models.device import DEVICE_STATUS_OFFLINE, DEVICE_STATUS_ONLINE, DEVICE_STATUS_STREAMING
from app.services import mediamtx, recordings
from app.services.devices import device_status_message
from app.services.hub import hub
from app.utils import utcnow

logger = logging.getLogger("onevideo.tracker")


class UsageTracker:
    def __init__(self, interval_seconds: int | None = None) -> None:
        self.interval = interval_seconds or settings.usage_tracker_interval_seconds

    async def run(self) -> None:
        logger.info("Tracker de uso iniciado (cada %s s)", self.interval)
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error en el ciclo del tracker de uso")
            await asyncio.sleep(self.interval)

    async def poll_once(self) -> None:
        # Cada fase se protege por separado: un fallo de red en una no debe
        # impedir la otra (ni tumbar el loop; se reintenta en el próximo ciclo).
        try:
            active_ids = await self._fetch_active_device_ids()
            # SQLAlchemy sync: el trabajo de DB va a un thread para no bloquear el loop.
            notifications = await asyncio.to_thread(self._sync_sessions, active_ids)
            for user_id, message in notifications:
                await hub.broadcast_to_user(user_id, message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error al sincronizar las sesiones de streaming")
        try:
            await self.reconcile_recordings()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error al reconciliar la grabación con MediaMTX")

    async def reconcile_recordings(self) -> None:
        """Alinea los path configs de MediaMTX con `devices.recording_on`."""
        # 1) Cuota: usuarios sobre su límite dejan de grabar en todos sus devices.
        notifications = await asyncio.to_thread(self._enforce_recording_quota)
        for user_id, message in notifications:
            await hub.broadcast_to_user(user_id, message)
        # 2) Estado deseado (DB) vs. configs explícitos cargados en MediaMTX.
        desired_ids = await asyncio.to_thread(self._recording_device_ids)
        configured = await mediamtx.list_live_path_configs()
        # Cada llamada a MediaMTX va en su propio try/except: un fallo puntual en
        # un device no debe impedir reconciliar el resto en el mismo ciclo (lo que
        # falle se reintenta en el próximo).
        for device_id in desired_ids:
            if configured.get(mediamtx.path_name(device_id)) is not True:
                try:
                    await mediamtx.set_recording(device_id, True)
                except Exception:
                    logger.warning(
                        "No se pudo activar la grabación del device %s en MediaMTX; "
                        "se reintentará en el próximo ciclo.",
                        device_id,
                    )
        for name in configured:
            try:
                device_id = uuid.UUID(name.split("/", 1)[1])
            except ValueError:
                device_id = None
            if device_id is None or device_id not in desired_ids:
                try:
                    await mediamtx.delete_path_config(name)
                except Exception:
                    logger.warning(
                        "No se pudo eliminar el path config %s en MediaMTX; "
                        "se reintentará en el próximo ciclo.",
                        name,
                    )

    def _enforce_recording_quota(self) -> list[tuple[uuid.UUID, dict]]:
        """Apaga la grabación de los usuarios que superaron su cuota de almacenamiento."""
        notifications: list[tuple[uuid.UUID, dict]] = []
        with database.SessionLocal() as db:
            recording_devices = db.scalars(
                select(Device).where(Device.recording_on.is_(True))
            ).all()
            by_user: dict[uuid.UUID, list[Device]] = {}
            for device in recording_devices:
                by_user.setdefault(device.user_id, []).append(device)
            for user_id, devices in by_user.items():
                user = db.get(User, user_id)
                if user is None:
                    continue
                all_device_ids = list(
                    db.scalars(select(Device.id).where(Device.user_id == user_id))
                )
                used = recordings.used_bytes_for_devices(all_device_ids)
                if used < recordings.limit_bytes_for_plan(user.plan):
                    continue
                logger.info(
                    "Cuota de grabaciones superada por %s: se apaga la grabación "
                    "en %s dispositivo(s).",
                    user.email,
                    len(devices),
                )
                for device in devices:
                    device.recording_on = False
                    notifications.append((user_id, device_status_message(device)))
            db.commit()
        return notifications

    def _recording_device_ids(self) -> set[uuid.UUID]:
        with database.SessionLocal() as db:
            return set(db.scalars(select(Device.id).where(Device.recording_on.is_(True))))

    async def _fetch_active_device_ids(self) -> set[uuid.UUID]:
        active: set[uuid.UUID] = set()
        base = settings.mediamtx_api_url.rstrip("/")
        async with httpx.AsyncClient(timeout=10) as client:
            page = 0
            while True:
                response = await client.get(
                    f"{base}/v3/paths/list", params={"itemsPerPage": 100, "page": page}
                )
                response.raise_for_status()
                data = response.json()
                for item in data.get("items") or []:
                    name = item.get("name") or ""
                    if not name.startswith("live/") or item.get("source") is None:
                        continue
                    try:
                        active.add(uuid.UUID(name.split("/", 1)[1]))
                    except ValueError:
                        continue
                page += 1
                if page >= int(data.get("pageCount") or 1):
                    break
        return active

    def _sync_sessions(self, active_ids: set[uuid.UUID]) -> list[tuple[uuid.UUID, dict]]:
        now = utcnow()
        notifications: list[tuple[uuid.UUID, dict]] = []
        with database.SessionLocal() as db:
            open_sessions = db.scalars(
                select(StreamSession).where(StreamSession.ended_at.is_(None))
            ).all()
            open_by_device = {session.device_id: session for session in open_sessions}

            # Cierra sesiones de paths que dejaron de publicar.
            for device_id, session in open_by_device.items():
                if device_id in active_ids:
                    continue
                session.ended_at = now
                device = db.get(Device, device_id)
                if device is not None and device.status == DEVICE_STATUS_STREAMING:
                    device.status = (
                        DEVICE_STATUS_ONLINE
                        if hub.is_device_connected(device.id)
                        else DEVICE_STATUS_OFFLINE
                    )
                    notifications.append((device.user_id, device_status_message(device)))

            # Abre sesiones para paths activos sin sesión abierta.
            for device_id in active_ids:
                if device_id in open_by_device:
                    continue
                device = db.get(Device, device_id)
                if device is None:
                    continue
                db.add(StreamSession(device_id=device_id, started_at=now))
                if device.status != DEVICE_STATUS_STREAMING:
                    device.status = DEVICE_STATUS_STREAMING
                    notifications.append((device.user_id, device_status_message(device)))

            db.commit()
        return notifications


usage_tracker = UsageTracker()

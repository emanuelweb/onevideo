"""Cliente de la API de configuración de MediaMTX (:9997) para la grabación por path.

MediaMTX graba nativamente: `record` está apagado en `pathDefaults` y se enciende
por path en runtime creando un config explícito `live/<device_uuid>` con
`{"record": true}`. El nombre del path va URL-encodeado en la ruta (la barra como
%2F). Esa config runtime vive en memoria: si el contenedor se reinicia se pierde,
por eso la verdad está en `devices.recording_on` y el tracker reconcilia.

Endpoints (Control API v3, verificados contra el OpenAPI oficial):
- POST   /v3/config/paths/add/{name}     crea el config (falla si ya existe)
- PATCH  /v3/config/paths/patch/{name}   modifica un config existente
- DELETE /v3/config/paths/delete/{name}  elimina el config (vuelve al catch-all)
- GET    /v3/config/paths/list           lista los configs explícitos (paginado)
"""
import urllib.parse
import uuid

import httpx

from app.config import settings

REQUEST_TIMEOUT_SECONDS = 10


def _api_base() -> str:
    return settings.mediamtx_api_url.rstrip("/")


def path_name(device_id: uuid.UUID) -> str:
    return f"live/{device_id}"


def _encoded_name(name: str) -> str:
    # La barra de `live/<uuid>` debe viajar como %2F dentro del segmento de URL.
    return urllib.parse.quote(name, safe="")


async def enable_recording(device_id: uuid.UUID) -> None:
    """Crea (o actualiza, si ya existe) el path config con record=true."""
    name = _encoded_name(path_name(device_id))
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{_api_base()}/v3/config/paths/add/{name}", json={"record": True}
        )
        if response.status_code >= 400:
            # El config ya existe (u otro conflicto): se parcha el existente.
            response = await client.patch(
                f"{_api_base()}/v3/config/paths/patch/{name}", json={"record": True}
            )
            response.raise_for_status()


async def disable_recording(device_id: uuid.UUID) -> None:
    await delete_path_config(path_name(device_id))


async def delete_path_config(name: str) -> None:
    """Elimina un config explícito; el path vuelve a caer en el regex catch-all."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.delete(
            f"{_api_base()}/v3/config/paths/delete/{_encoded_name(name)}"
        )
        if response.status_code >= 400 and response.status_code != 404:
            response.raise_for_status()


async def set_recording(device_id: uuid.UUID, enabled: bool) -> None:
    if enabled:
        await enable_recording(device_id)
    else:
        await disable_recording(device_id)


async def list_live_path_configs() -> dict[str, bool]:
    """Configs explícitos `live/*` actualmente cargados: {nombre: record activado}."""
    configs: dict[str, bool] = {}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        page = 0
        while True:
            response = await client.get(
                f"{_api_base()}/v3/config/paths/list",
                params={"itemsPerPage": 100, "page": page},
            )
            response.raise_for_status()
            data = response.json()
            for item in data.get("items") or []:
                name = item.get("name") or ""
                if name.startswith("live/"):
                    configs[name] = bool(item.get("record"))
            page += 1
            if page >= int(data.get("pageCount") or 1):
                break
    return configs

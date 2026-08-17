"""Hub en memoria de conexiones WebSocket: dispositivos y consolas (dashboard).

Vive en un único proceso/loop de asyncio; por eso la API corre con un solo worker.
"""
import asyncio
import uuid
from typing import Any

from fastapi import WebSocket


class ConnectionHub:
    def __init__(self) -> None:
        self._devices: dict[uuid.UUID, WebSocket] = {}
        self._consoles: dict[uuid.UUID, set[WebSocket]] = {}
        self._telemetry: dict[uuid.UUID, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    # --- Dispositivos ---

    async def register_device(self, device_id: uuid.UUID, websocket: WebSocket) -> WebSocket | None:
        """Registra el WS del dispositivo; devuelve el WS anterior si existía."""
        async with self._lock:
            previous = self._devices.get(device_id)
            self._devices[device_id] = websocket
        return previous if previous is not websocket else None

    async def unregister_device(self, device_id: uuid.UUID, websocket: WebSocket) -> bool:
        """Quita el WS solo si sigue siendo el registrado (evita pisar reconexiones)."""
        async with self._lock:
            if self._devices.get(device_id) is websocket:
                del self._devices[device_id]
                self._telemetry.pop(device_id, None)
                return True
        return False

    def is_device_connected(self, device_id: uuid.UUID) -> bool:
        return device_id in self._devices

    def set_telemetry(self, device_id: uuid.UUID, telemetry: dict[str, Any]) -> None:
        self._telemetry[device_id] = telemetry

    def get_telemetry(self, device_id: uuid.UUID) -> dict[str, Any] | None:
        return self._telemetry.get(device_id)

    async def send_to_device(self, device_id: uuid.UUID, message: dict) -> bool:
        websocket = self._devices.get(device_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            await self.unregister_device(device_id, websocket)
            return False

    async def close_device(self, device_id: uuid.UUID) -> None:
        websocket = self._devices.get(device_id)
        if websocket is not None:
            try:
                await websocket.close(code=1000)
            except Exception:
                pass

    # --- Consolas ---

    async def register_console(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._consoles.setdefault(user_id, set()).add(websocket)

    async def unregister_console(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._consoles.get(user_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    del self._consoles[user_id]

    async def broadcast_to_user(self, user_id: uuid.UUID, message: dict) -> None:
        async with self._lock:
            targets = list(self._consoles.get(user_id, ()))
        dead: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            await self.unregister_console(user_id, websocket)


hub = ConnectionHub()

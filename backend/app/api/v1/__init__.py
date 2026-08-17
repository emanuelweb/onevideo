from fastapi import APIRouter

from app.api.v1 import admin, auth, devices, internal, pairing, plans, usage, ws

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(plans.router, tags=["plans"])
api_router.include_router(usage.router, tags=["usage"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(pairing.router, prefix="/pairing", tags=["pairing"])
api_router.include_router(internal.router, prefix="/internal", tags=["internal"])
api_router.include_router(ws.router, tags=["websockets"])

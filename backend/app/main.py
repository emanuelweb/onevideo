"""Punto de entrada de la API de OneVideo."""
import asyncio
import contextlib

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.config import settings
from app.services.tracker import usage_tracker


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    tracker_task: asyncio.Task | None = None
    if settings.usage_tracker_enabled:
        tracker_task = asyncio.create_task(usage_tracker.run(), name="usage-tracker")
    yield
    if tracker_task is not None:
        tracker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tracker_task


app = FastAPI(title="OneVideo API", version="1.0.0", lifespan=lifespan)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: list[str] = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", [])]
        if loc and loc[0] in ("body", "query", "path", "header"):
            loc = loc[1:]
        if loc:
            fields.append(".".join(loc))
    detail = "Datos de entrada inválidos."
    if fields:
        detail = f"Datos de entrada inválidos: {', '.join(dict.fromkeys(fields))}."
    return JSONResponse(status_code=422, content={"detail": detail})


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"status": "ok"}

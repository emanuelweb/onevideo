from pydantic import BaseModel, ConfigDict


class MediaMTXAuthPayload(BaseModel):
    """Payload que envía MediaMTX en su hook de autenticación externa."""

    model_config = ConfigDict(extra="ignore")

    user: str | None = None
    password: str | None = None
    token: str | None = None
    ip: str | None = None
    action: str
    path: str | None = None
    protocol: str | None = None
    id: str | None = None
    query: str | None = None

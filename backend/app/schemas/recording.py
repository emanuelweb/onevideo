from datetime import datetime

from pydantic import BaseModel


class RecordingPublic(BaseModel):
    # rid: filename en base64url sin padding.
    id: str
    filename: str
    started_at: datetime | None
    size_bytes: int
    in_progress: bool


class RecordingList(BaseModel):
    items: list[RecordingPublic]
    used_bytes: int
    limit_bytes: int


class RecordingToggleRequest(BaseModel):
    enabled: bool


class DownloadTokenResponse(BaseModel):
    url: str
    expires_at: datetime

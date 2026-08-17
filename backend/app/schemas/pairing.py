import uuid
from typing import Literal

from pydantic import BaseModel, Field


class PairingClaimRequest(BaseModel):
    code: str = Field(min_length=8, max_length=8)
    platform: Literal["android"]
    model: str = Field(min_length=1, max_length=120)


class PairingClaimResponse(BaseModel):
    device_id: uuid.UUID
    device_token: str
    whip_url: str
    ws_url: str

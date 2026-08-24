import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Resolution = Literal["720p", "1080p"]
Fps = Literal[30, 60]
Facing = Literal["front", "back"]
DeviceStatus = Literal["online", "offline", "streaming"]
CommandType = Literal[
    "camera_on",
    "camera_off",
    "switch_camera",
    "set_quality",
    "torch_on",
    "torch_off",
    "restart_stream",
]


class DeviceSettings(BaseModel):
    resolution: Resolution = "720p"
    fps: Fps = 30
    bitrate_kbps: int = Field(default=2500, gt=0, le=50000)
    facing: Facing = "back"


class DeviceSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: Resolution | None = None
    fps: Fps | None = None
    bitrate_kbps: int | None = Field(default=None, gt=0, le=50000)
    facing: Facing | None = None


class DeviceTelemetry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    battery: int | None = Field(default=None, ge=0, le=100)
    temp_c: float | None = None
    charging: bool | None = None
    network: str | None = None
    bitrate_kbps: int | None = Field(default=None, ge=0)
    resolution: str | None = None
    facing: str | None = None


class DevicePublic(BaseModel):
    id: uuid.UUID
    name: str
    platform: str | None
    model: str | None
    status: DeviceStatus
    camera_on: bool
    recording_on: bool
    last_seen_at: datetime | None
    created_at: datetime
    telemetry: DeviceTelemetry | None
    settings: DeviceSettings


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    settings: DeviceSettingsPatch | None = None


class DeviceWithPairing(DevicePublic):
    pairing_code: str
    pairing_expires_at: datetime


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class SetQualityPayload(BaseModel):
    resolution: Resolution
    fps: Fps
    bitrate_kbps: int = Field(gt=0, le=50000)


class CommandRequest(BaseModel):
    type: CommandType
    payload: dict[str, Any] | None = None


class CommandResponse(BaseModel):
    delivered: bool
    command_id: uuid.UUID


class StreamInfo(BaseModel):
    whip_url: str
    whep_url: str
    player_url: str
    view_token: str

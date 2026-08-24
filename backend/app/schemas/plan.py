from pydantic import BaseModel, ConfigDict


class PlanPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    price_usd_month: float
    max_devices: int
    max_resolution: str
    max_fps: int
    monthly_hours: int | None
    max_recording_gb: int
    features: list[str]

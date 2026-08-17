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
    features: list[str]

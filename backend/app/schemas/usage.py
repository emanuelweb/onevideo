from datetime import datetime

from pydantic import BaseModel


class UsageResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    hours_used: float
    hours_limit: int | None
    devices_used: int
    devices_limit: int

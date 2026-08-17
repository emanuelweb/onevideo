import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plan import PlanPublic


class AdminUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    is_superadmin: bool
    created_at: datetime
    plan: PlanPublic
    plan_source: str
    plan_expires_at: datetime | None
    devices_count: int
    hours_used_month: float


class AdminUserList(BaseModel):
    total: int
    items: list[AdminUser]


class AdminPlanAssign(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)
    # Vacío o ausente = plan sin vencimiento.
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_superadmin: bool | None = None


class PlanGrantPublic(BaseModel):
    id: int
    plan_code: str
    plan_name: str
    source: str
    granted_by_email: str | None
    expires_at: datetime | None
    note: str | None
    created_at: datetime


class AdminPlanCount(BaseModel):
    plan_code: str
    plan_name: str
    count: int


class AdminStats(BaseModel):
    users_total: int
    users_active: int
    devices_total: int
    devices_streaming: int
    hours_this_month: float
    users_by_plan: list[AdminPlanCount]

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.plan import PlanPublic


# Secreto opcional para el bootstrap del primer super-admin (ver services/admin.py).
# La UI no lo pide: lo envía quien despliega, una sola vez, desde la línea de comandos.
BOOTSTRAP_TOKEN_FIELD = Field(
    default=None,
    max_length=200,
    description="Secreto SUPERADMIN_BOOTSTRAP_TOKEN para el bootstrap del primer administrador.",
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=120)
    bootstrap_token: str | None = BOOTSTRAP_TOKEN_FIELD


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
    bootstrap_token: str | None = BOOTSTRAP_TOKEN_FIELD


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    plan: PlanPublic
    is_superadmin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserPublic

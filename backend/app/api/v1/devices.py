import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Device, Plan, User
from app.schemas import (
    CommandRequest,
    CommandResponse,
    DeviceCreate,
    DevicePublic,
    DeviceSettings,
    DeviceUpdate,
    DeviceWithPairing,
    PairingCodeResponse,
    SetQualityPayload,
    StreamInfo,
)
from app.security import generate_opaque_token
from app.services.devices import (
    RESOLUTION_RANK,
    default_settings_for_plan,
    device_public,
    notify_consoles,
)
from app.services.hub import hub
from app.services.pairing import issue_pairing_code
from app.services.streaming import build_stream_info

router = APIRouter()


def _get_owned_device(db: Session, user: User, device_id: uuid.UUID) -> Device:
    device = db.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return device


def _validate_quality_against_plan(resolution: str, fps: int, plan: Plan) -> None:
    if (
        RESOLUTION_RANK.get(resolution, 0) > RESOLUTION_RANK.get(plan.max_resolution, 0)
        or fps > plan.max_fps
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Tu plan permite hasta {plan.max_resolution} a {plan.max_fps} fps.",
        )


@router.get("", response_model=list[DevicePublic])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DevicePublic]:
    devices = db.scalars(
        select(Device).where(Device.user_id == current_user.id).order_by(Device.created_at)
    ).all()
    return [device_public(device) for device in devices]


@router.post("", response_model=DeviceWithPairing)
def create_device(
    body: DeviceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceWithPairing:
    count = (
        db.scalar(select(func.count()).select_from(Device).where(Device.user_id == current_user.id))
        or 0
    )
    if count >= current_user.plan.max_devices:
        raise HTTPException(status_code=403, detail="Alcanzaste el límite de dispositivos de tu plan.")
    device = Device(
        user_id=current_user.id,
        name=body.name.strip(),
        view_token=generate_opaque_token(),
        settings=default_settings_for_plan(current_user.plan),
    )
    db.add(device)
    db.flush()
    pairing = issue_pairing_code(db, device.id)
    db.commit()
    public = device_public(device)
    return DeviceWithPairing(
        **public.model_dump(),
        pairing_code=pairing.code,
        pairing_expires_at=pairing.expires_at,
    )


@router.get("/{device_id}", response_model=DevicePublic)
def get_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DevicePublic:
    return device_public(_get_owned_device(db, current_user, device_id))


@router.patch("/{device_id}", response_model=DevicePublic)
async def update_device(
    device_id: uuid.UUID,
    body: DeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DevicePublic:
    device = _get_owned_device(db, current_user, device_id)
    if body.name is not None:
        device.name = body.name.strip()
    if body.settings is not None:
        patch = {key: value for key, value in body.settings.model_dump().items() if value is not None}
        try:
            merged = DeviceSettings(**{**(device.settings or {}), **patch})
        except ValidationError:
            raise HTTPException(status_code=422, detail="Configuración de dispositivo inválida.")
        _validate_quality_against_plan(merged.resolution, merged.fps, current_user.plan)
        device.settings = merged.model_dump()
    db.commit()
    await notify_consoles(device)
    return device_public(device)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    device = _get_owned_device(db, current_user, device_id)
    await hub.close_device(device.id)
    db.delete(device)
    db.commit()
    return Response(status_code=204)


@router.post("/{device_id}/pairing-code", response_model=PairingCodeResponse)
def regenerate_pairing_code(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PairingCodeResponse:
    device = _get_owned_device(db, current_user, device_id)
    pairing = issue_pairing_code(db, device.id)
    db.commit()
    return PairingCodeResponse(code=pairing.code, expires_at=pairing.expires_at)


@router.post("/{device_id}/commands", response_model=CommandResponse)
async def send_command(
    device_id: uuid.UUID,
    body: CommandRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommandResponse:
    device = _get_owned_device(db, current_user, device_id)
    payload = body.payload
    if body.type == "set_quality":
        if payload is None:
            raise HTTPException(status_code=422, detail="El comando set_quality requiere payload.")
        try:
            quality = SetQualityPayload(**payload)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Payload de set_quality inválido.")
        _validate_quality_against_plan(quality.resolution, quality.fps, current_user.plan)
        payload = quality.model_dump()
    command_id = uuid.uuid4()
    delivered = await hub.send_to_device(
        device.id,
        {
            "type": "command",
            "payload": {"command_id": str(command_id), "type": body.type, "payload": payload},
        },
    )
    return CommandResponse(delivered=delivered, command_id=command_id)


@router.get("/{device_id}/stream", response_model=StreamInfo)
def get_stream_info(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamInfo:
    return build_stream_info(_get_owned_device(db, current_user, device_id))


@router.post("/{device_id}/view-token/rotate", response_model=StreamInfo)
def rotate_view_token(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamInfo:
    device = _get_owned_device(db, current_user, device_id)
    device.view_token = generate_opaque_token()
    db.commit()
    return build_stream_info(device)

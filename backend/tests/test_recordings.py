"""Tests de la grabación en la nube: toggle, listado, descarga, borrado y reconciliación."""
import asyncio
import base64
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app import db as database
from app.config import settings
from app.models import Device, Plan, User
from app.services.recordings import encode_rid
from app.services.tracker import UsageTracker

PASSWORD = "clave-segura-123"
VALID_FILENAME = "2026-08-24_10-00-00-000000.mp4"


@pytest.fixture()
def recordings_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path))
    return tmp_path


@pytest.fixture()
def mediamtx_spy(monkeypatch):
    calls = []

    async def fake_set_recording(device_id, enabled):
        calls.append((device_id, enabled))

    monkeypatch.setattr("app.services.mediamtx.set_recording", fake_set_recording)
    return calls


def _register(client, email="streamer@example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Usuaria de Prueba"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_device(client, token, name="Cámara principal"):
    response = client.post("/api/v1/devices", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200
    return response.json()["id"]


def _device_dir(root, device_id):
    directory = root / "live" / str(device_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _make_recording(directory, filename=VALID_FILENAME, content=b"x" * 100, age_seconds=3600):
    path = directory / filename
    path.write_bytes(content)
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(path, (old, old))
    return path


def _set_plan_quota(session_factory, code, gb):
    with session_factory() as db:
        plan = db.scalar(select(Plan).where(Plan.code == code))
        plan.max_recording_gb = gb
        db.commit()


# --- Toggle de grabación ---------------------------------------------------------


def test_toggle_recording_on_off_updates_device_and_calls_mediamtx(
    client, recordings_root, mediamtx_spy
):
    token = _register(client)
    device_id = _create_device(client, token)

    response = client.post(
        f"/api/v1/devices/{device_id}/recording", json={"enabled": True}, headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["recording_on"] is True

    # Persistido: un GET posterior lo sigue mostrando encendido.
    response = client.get(f"/api/v1/devices/{device_id}", headers=_auth(token))
    assert response.json()["recording_on"] is True

    response = client.post(
        f"/api/v1/devices/{device_id}/recording", json={"enabled": False}, headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["recording_on"] is False

    assert mediamtx_spy == [(uuid.UUID(device_id), True), (uuid.UUID(device_id), False)]


def test_toggle_recording_persists_even_if_mediamtx_fails(client, recordings_root, monkeypatch):
    async def failing_set_recording(device_id, enabled):
        raise RuntimeError("MediaMTX caído")

    monkeypatch.setattr("app.services.mediamtx.set_recording", failing_set_recording)
    token = _register(client)
    device_id = _create_device(client, token)
    response = client.post(
        f"/api/v1/devices/{device_id}/recording", json={"enabled": True}, headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["recording_on"] is True


def test_toggle_recording_over_quota_returns_403(
    client, session_factory, recordings_root, mediamtx_spy
):
    _set_plan_quota(session_factory, "free", 0)
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))

    response = client.post(
        f"/api/v1/devices/{device_id}/recording", json={"enabled": True}, headers=_auth(token)
    )
    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Alcanzaste el almacenamiento de grabaciones de tu plan. "
        "Elimina grabaciones o mejora tu plan."
    )
    assert mediamtx_spy == []
    # Apagar sigue permitido aunque esté sobre cuota.
    response = client.post(
        f"/api/v1/devices/{device_id}/recording", json={"enabled": False}, headers=_auth(token)
    )
    assert response.status_code == 200


def test_toggle_recording_requires_owned_device(client, recordings_root, mediamtx_spy):
    token = _register(client)
    response = client.post(
        f"/api/v1/devices/{uuid.uuid4()}/recording", json={"enabled": True}, headers=_auth(token)
    )
    assert response.status_code == 404


# --- Listado ---------------------------------------------------------------------


def test_list_recordings_from_directory(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    directory = _device_dir(recordings_root, device_id)
    _make_recording(directory, "2026-08-24_10-00-00-000000.mp4", b"a" * 10)
    _make_recording(directory, "2026-08-24_11-00-00-000000.mp4", b"b" * 20)
    # Nombre válido pero sin timestamp parseable → started_at null.
    _make_recording(directory, "video.mp4", b"c" * 5)
    # Inválidos: se ignoran.
    _make_recording(directory, "notas.txt", b"nope")
    (directory / "subdir").mkdir()

    response = client.get(f"/api/v1/devices/{device_id}/recordings", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    filenames = [item["filename"] for item in data["items"]]
    assert filenames == [
        "video.mp4",
        "2026-08-24_11-00-00-000000.mp4",
        "2026-08-24_10-00-00-000000.mp4",
    ]
    by_name = {item["filename"]: item for item in data["items"]}
    assert by_name["2026-08-24_11-00-00-000000.mp4"]["size_bytes"] == 20
    assert by_name["2026-08-24_11-00-00-000000.mp4"]["started_at"].startswith("2026-08-24T11:00:00")
    assert by_name["2026-08-24_11-00-00-000000.mp4"]["in_progress"] is False
    assert by_name["video.mp4"]["started_at"] is None
    assert by_name["video.mp4"]["id"] == encode_rid("video.mp4")
    assert data["used_bytes"] == 35
    assert data["limit_bytes"] == 1 * 1024**3


def test_list_recordings_empty_without_directory(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    response = client.get(f"/api/v1/devices/{device_id}/recordings", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["used_bytes"] == 0


def test_recent_file_is_reported_in_progress(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id), age_seconds=0)
    response = client.get(f"/api/v1/devices/{device_id}/recordings", headers=_auth(token))
    assert response.json()["items"][0]["in_progress"] is True


# --- rid anti-traversal ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw_filename",
    [
        "../../etc/passwd.mp4",
        "..\\secreto.mp4",
        "/etc/passwd.mp4",
        "C:\\Windows\\evil.mp4",
        "sin_extension",
        "notas.txt",
        "..mp4",
    ],
)
def test_rid_traversal_or_invalid_names_return_404(client, recordings_root, raw_filename):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))
    rid = base64.urlsafe_b64encode(raw_filename.encode()).decode().rstrip("=")
    response = client.post(
        f"/api/v1/devices/{device_id}/recordings/{rid}/download-token", headers=_auth(token)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Grabación no encontrada."


def test_rid_not_base64_returns_404(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    response = client.delete(
        f"/api/v1/devices/{device_id}/recordings/%2e%2e%2Fx", headers=_auth(token)
    )
    assert response.status_code == 404


# --- download-token y descarga ---------------------------------------------------


def _issue_download_url(client, token, device_id, rid):
    response = client.post(
        f"/api/v1/devices/{device_id}/recordings/{rid}/download-token", headers=_auth(token)
    )
    assert response.status_code == 200
    return response.json()["url"]


def test_download_token_url_downloads_without_auth_header(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    content = bytes(range(256)) * 2
    _make_recording(_device_dir(recordings_root, device_id), content=content)
    rid = encode_rid(VALID_FILENAME)

    url = _issue_download_url(client, token, device_id, rid)
    assert f"/api/v1/devices/{device_id}/recordings/{rid}/download?token=" in url

    response = client.get(url)  # sin header Authorization
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert VALID_FILENAME in response.headers["content-disposition"]
    assert response.headers["content-disposition"].startswith("inline")


def test_download_with_range_returns_206_and_exact_bytes(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    content = bytes(range(100))
    _make_recording(_device_dir(recordings_root, device_id), content=content)
    rid = encode_rid(VALID_FILENAME)
    url = _issue_download_url(client, token, device_id, rid)

    response = client.get(url, headers={"Range": "bytes=10-19"})
    assert response.status_code == 206
    assert response.content == content[10:20]
    assert response.headers["content-range"] == "bytes 10-19/100"
    assert response.headers["content-length"] == "10"

    # Rango abierto y rango sufijo.
    response = client.get(url, headers={"Range": "bytes=90-"})
    assert response.status_code == 206
    assert response.content == content[90:]
    assert response.headers["content-range"] == "bytes 90-99/100"

    response = client.get(url, headers={"Range": "bytes=-5"})
    assert response.status_code == 206
    assert response.content == content[-5:]

    # Rango fuera del archivo → 416.
    response = client.get(url, headers={"Range": "bytes=200-300"})
    assert response.status_code == 416


def test_download_with_malformed_range_is_ignored(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    content = bytes(range(100))
    _make_recording(_device_dir(recordings_root, device_id), content=content)
    rid = encode_rid(VALID_FILENAME)
    url = _issue_download_url(client, token, device_id, rid)

    # Un Range no parseable se ignora (RFC 7233): 200 con el archivo completo.
    for header in ("bytes=abc", "bytes=-", "bytes=", "otros=0-1"):
        response = client.get(url, headers={"Range": header})
        assert response.status_code == 200, header
        assert response.content == content


def test_download_with_expired_token_returns_401(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))
    rid = encode_rid(VALID_FILENAME)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000000",
            "scope": "recording",
            "device_id": device_id,
            "rid": rid,
            "exp": past,
        },
        settings.secret_key,
        algorithm="HS256",
    )
    response = client.get(
        f"/api/v1/devices/{device_id}/recordings/{rid}/download?token={expired}"
    )
    assert response.status_code == 401


def test_download_with_access_token_scope_returns_401(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))
    rid = encode_rid(VALID_FILENAME)
    # Un JWT de sesión válido no sirve: no tiene scope "recording".
    response = client.get(
        f"/api/v1/devices/{device_id}/recordings/{rid}/download?token={token}"
    )
    assert response.status_code == 401


def test_download_token_is_not_a_session_token(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))
    rid = encode_rid(VALID_FILENAME)
    url = _issue_download_url(client, token, device_id, rid)
    download_token = url.split("token=", 1)[1]
    # Separación de scopes en ambos sentidos: el token de descarga (scope
    # "recording") no debe servir como bearer de sesión en el resto de la API.
    response = client.get("/api/v1/auth/me", headers=_auth(download_token))
    assert response.status_code == 401
    response = client.get(f"/api/v1/devices/{device_id}", headers=_auth(download_token))
    assert response.status_code == 401


def test_uvicorn_access_log_redacts_download_token():
    # El access log de uvicorn escribiría la URL completa (con token=) a los
    # logs de docker; el filtro de app.main debe redactar el valor del token.
    from app.main import RedactTokenQueryFilter

    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "203.0.113.7:4242",
            "GET",
            "/api/v1/devices/abc/recordings/xyz/download?token=eyJhbGciOi.secreto.firma",
            "1.1",
            200,
        ),
        exc_info=None,
    )
    assert RedactTokenQueryFilter().filter(record) is True
    message = record.getMessage()
    assert "secreto" not in message
    assert "token=[REDACTADO]" in message


def test_download_token_of_another_device_returns_404(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    _make_recording(_device_dir(recordings_root, device_id))
    rid = encode_rid(VALID_FILENAME)
    url = _issue_download_url(client, token, device_id, rid)
    download_token = url.split("token=", 1)[1]
    response = client.get(
        f"/api/v1/devices/{uuid.uuid4()}/recordings/{rid}/download?token={download_token}"
    )
    assert response.status_code == 404


def test_download_token_requires_existing_recording(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    rid = encode_rid("2026-01-01_00-00-00-000000.mp4")
    response = client.post(
        f"/api/v1/devices/{device_id}/recordings/{rid}/download-token", headers=_auth(token)
    )
    assert response.status_code == 404


# --- DELETE ----------------------------------------------------------------------


def test_delete_recording_removes_file(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    path = _make_recording(_device_dir(recordings_root, device_id))
    rid = encode_rid(VALID_FILENAME)
    response = client.delete(
        f"/api/v1/devices/{device_id}/recordings/{rid}", headers=_auth(token)
    )
    assert response.status_code == 204
    assert not path.exists()


def test_delete_in_progress_recording_returns_409(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    path = _make_recording(_device_dir(recordings_root, device_id), age_seconds=0)
    rid = encode_rid(VALID_FILENAME)
    response = client.delete(
        f"/api/v1/devices/{device_id}/recordings/{rid}", headers=_auth(token)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Esa grabación está en curso. Detén la grabación antes de eliminarla."
    )
    assert path.exists()


def test_delete_missing_recording_returns_404(client, recordings_root):
    token = _register(client)
    device_id = _create_device(client, token)
    rid = encode_rid("2026-01-01_00-00-00-000000.mp4")
    response = client.delete(
        f"/api/v1/devices/{device_id}/recordings/{rid}", headers=_auth(token)
    )
    assert response.status_code == 404


# --- Reconciliador ---------------------------------------------------------------


def _make_user_with_device(session_factory, recording_on=True):
    with session_factory() as db:
        plan = db.scalar(select(Plan).where(Plan.code == "free"))
        user = User(
            email=f"user-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash-de-prueba",
            name="Usuaria de Prueba",
            plan_id=plan.id,
        )
        db.add(user)
        db.flush()
        device = Device(
            user_id=user.id,
            name="Cámara",
            view_token="view-token-de-prueba",
            recording_on=recording_on,
        )
        db.add(device)
        db.commit()
        return user.id, device.id


def _patch_mediamtx(monkeypatch, configured):
    set_calls, deleted = [], []

    async def fake_list():
        return dict(configured)

    async def fake_set(device_id, enabled):
        set_calls.append((device_id, enabled))

    async def fake_delete(name):
        deleted.append(name)

    monkeypatch.setattr("app.services.mediamtx.list_live_path_configs", fake_list)
    monkeypatch.setattr("app.services.mediamtx.set_recording", fake_set)
    monkeypatch.setattr("app.services.mediamtx.delete_path_config", fake_delete)
    return set_calls, deleted


def test_reconciler_disables_recording_for_user_over_quota(
    session_factory, recordings_root, monkeypatch
):
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    _set_plan_quota(session_factory, "free", 0)
    _, device_id = _make_user_with_device(session_factory)
    _make_recording(_device_dir(recordings_root, device_id))
    set_calls, deleted = _patch_mediamtx(monkeypatch, {f"live/{device_id}": True})

    asyncio.run(UsageTracker().reconcile_recordings())

    with session_factory() as db:
        assert db.get(Device, device_id).recording_on is False
    assert set_calls == []
    assert deleted == [f"live/{device_id}"]


def test_reconciler_adds_missing_config_and_removes_orphans(
    session_factory, recordings_root, monkeypatch
):
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    _, device_id = _make_user_with_device(session_factory)
    orphan = f"live/{uuid.uuid4()}"
    set_calls, deleted = _patch_mediamtx(monkeypatch, {orphan: True})

    asyncio.run(UsageTracker().reconcile_recordings())

    with session_factory() as db:
        assert db.get(Device, device_id).recording_on is True
    assert set_calls == [(device_id, True)]
    assert deleted == [orphan]


def test_reconciler_survives_per_device_mediamtx_failure(
    session_factory, recordings_root, monkeypatch
):
    # Un fallo puntual de MediaMTX en un device no debe abortar el resto del
    # ciclo: los huérfanos igual se eliminan y el loop no se cae.
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    _make_user_with_device(session_factory)
    orphan = f"live/{uuid.uuid4()}"
    deleted = []

    async def fake_list():
        return {orphan: True}

    async def failing_set(device_id, enabled):
        raise RuntimeError("timeout simulado")

    async def fake_delete(name):
        deleted.append(name)

    monkeypatch.setattr("app.services.mediamtx.list_live_path_configs", fake_list)
    monkeypatch.setattr("app.services.mediamtx.set_recording", failing_set)
    monkeypatch.setattr("app.services.mediamtx.delete_path_config", fake_delete)

    asyncio.run(UsageTracker().reconcile_recordings())

    assert deleted == [orphan]

"""Tests del hook interno de autenticación de MediaMTX (/internal/mediamtx/auth)."""
from app.config import settings

HOOK_PATH = "/api/v1/internal/mediamtx/auth"
API_PAYLOAD = {"action": "api", "ip": "10.0.0.5"}


def test_secret_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "mediamtx_auth_secret", "secreto-de-prueba")
    response = client.post(HOOK_PATH, json=API_PAYLOAD)
    assert response.status_code == 401


def test_wrong_secret_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "mediamtx_auth_secret", "secreto-de-prueba")
    response = client.post(f"{HOOK_PATH}?secret=incorrecto", json=API_PAYLOAD)
    assert response.status_code == 401


def test_correct_secret_allows_api_action(client, monkeypatch):
    monkeypatch.setattr(settings, "mediamtx_auth_secret", "secreto-de-prueba")
    response = client.post(f"{HOOK_PATH}?secret=secreto-de-prueba", json=API_PAYLOAD)
    assert response.status_code == 200
    assert response.json() == {"detail": "ok"}


def test_body_ip_not_trusted_when_secret_configured(client, monkeypatch):
    """Con secreto configurado, un body.ip 'interno' falsificado no autoriza nada."""
    monkeypatch.setattr(settings, "mediamtx_auth_secret", "secreto-de-prueba")
    response = client.post(HOOK_PATH, json={"action": "api", "ip": "10.0.0.1"})
    assert response.status_code == 401


def test_without_secret_internal_body_ip_allows_api_action(client):
    # Sin secreto (dev/tests): comportamiento previo basado en la IP reportada.
    response = client.post(HOOK_PATH, json={"action": "api", "ip": "172.18.0.4"})
    assert response.status_code == 200


def test_without_secret_external_body_ip_rejected(client):
    # Nota: no usar rangos de documentación (203.0.113.0/24): en Python >= 3.12.7
    # ipaddress los reporta como is_private=True.
    response = client.post(HOOK_PATH, json={"action": "api", "ip": "8.8.8.8"})
    assert response.status_code == 401


def test_publish_still_validates_device_token_with_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "mediamtx_auth_secret", "secreto-de-prueba")
    response = client.post(
        f"{HOOK_PATH}?secret=secreto-de-prueba",
        json={
            "action": "publish",
            "path": "live/00000000-0000-0000-0000-000000000000",
            "token": "Bearer token-invalido",
        },
    )
    assert response.status_code == 401

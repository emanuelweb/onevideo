"""Tests del panel de super-administración y de la degradación perezosa de planes."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.models import Plan, PlanGrant, User
from app.models.user import PLAN_SOURCE_ADMIN, PLAN_SOURCE_SIGNUP
from app.services.admin import ensure_bootstrap_superadmin
from app.services.plans import resolve_effective_plan
from app.utils import utcnow

PASSWORD = "clave-segura-123"
BOOTSTRAP_TOKEN = "secreto-de-bootstrap-para-pruebas"


def _register(client, email, name="Usuario de Prueba", bootstrap_token=None):
    body = {"email": email, "password": PASSWORD, "name": name}
    if bootstrap_token is not None:
        body["bootstrap_token"] = bootstrap_token
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 200
    return response.json()


def _login(client, email, bootstrap_token=None):
    body = {"email": email, "password": PASSWORD}
    if bootstrap_token is not None:
        body["bootstrap_token"] = bootstrap_token
    return client.post("/api/v1/auth/login", json=body)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _promote(session_factory, email):
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        user.is_superadmin = True
        db.commit()


def _admin_token(client, session_factory, email="admin@example.com"):
    token = _register(client, email, "Administradora")["access_token"]
    _promote(session_factory, email)
    return token


def _make_user(db, email, plan_code="free", **kwargs):
    plan = db.scalar(select(Plan).where(Plan.code == plan_code))
    user = User(
        email=email,
        password_hash="hash-de-prueba",
        name="Usuario de Prueba",
        plan_id=plan.id,
        **kwargs,
    )
    db.add(user)
    db.commit()
    return user


# --- Autorización ---------------------------------------------------------------


def test_admin_endpoints_require_authentication(client):
    assert client.get("/api/v1/admin/stats").status_code == 401
    assert client.get("/api/v1/admin/users").status_code == 401


def test_normal_user_gets_403_on_every_admin_endpoint(client, session_factory):
    token = _register(client, "normal@example.com")["access_token"]
    with session_factory() as db:
        other_id = _make_user(db, "otra@example.com").id

    paths = [
        ("get", "/api/v1/admin/stats"),
        ("get", "/api/v1/admin/users"),
        ("get", f"/api/v1/admin/users/{other_id}"),
        ("get", f"/api/v1/admin/users/{other_id}/grants"),
        ("delete", f"/api/v1/admin/users/{other_id}"),
    ]
    for method, path in paths:
        response = getattr(client, method)(path, headers=_auth(token))
        assert response.status_code == 403, path
        assert response.json()["detail"] == "Necesitas permisos de administrador."

    response = client.post(
        f"/api/v1/admin/users/{other_id}/plan", json={"plan_code": "pro"}, headers=_auth(token)
    )
    assert response.status_code == 403
    response = client.patch(
        f"/api/v1/admin/users/{other_id}", json={"is_active": False}, headers=_auth(token)
    )
    assert response.status_code == 403


# --- Listado y estadísticas -----------------------------------------------------


def test_superadmin_lists_users_with_total(client, session_factory):
    token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com", "Streamer LATAM")
    client.post("/api/v1/devices", json={"name": "Celular"}, headers=_auth(normal["access_token"]))

    response = client.get("/api/v1/admin/users", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Orden por created_at descendente: el último registrado va primero.
    first = data["items"][0]
    assert first["email"] == "streamer@example.com"
    assert first["devices_count"] == 1
    assert first["hours_used_month"] == 0.0
    assert first["plan"]["code"] == "free"
    assert first["plan_source"] == PLAN_SOURCE_SIGNUP
    assert first["plan_expires_at"] is None
    assert first["is_superadmin"] is False
    assert data["items"][1]["is_superadmin"] is True


def test_user_search_matches_email_and_name_case_insensitively(client, session_factory):
    token = _admin_token(client, session_factory)
    _register(client, "carla@example.com", "Carla Pérez")
    _register(client, "diego@otrodominio.com", "Diego Ruiz")

    by_name = client.get("/api/v1/admin/users?search=CARLA", headers=_auth(token)).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["email"] == "carla@example.com"

    by_email = client.get("/api/v1/admin/users?search=otrodominio", headers=_auth(token)).json()
    assert by_email["total"] == 1
    assert by_email["items"][0]["email"] == "diego@otrodominio.com"

    empty = client.get("/api/v1/admin/users?search=nadie", headers=_auth(token)).json()
    assert empty == {"total": 0, "items": []}


def test_stats_summarize_users_devices_and_plans(client, session_factory):
    token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    client.post("/api/v1/devices", json={"name": "Celular"}, headers=_auth(normal["access_token"]))

    response = client.get("/api/v1/admin/stats", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["users_total"] == 2
    assert data["users_active"] == 2
    assert data["devices_total"] == 1
    assert data["devices_streaming"] == 0
    assert data["hours_this_month"] == 0.0
    by_plan = {row["plan_code"]: row["count"] for row in data["users_by_plan"]}
    assert by_plan["free"] == 2
    assert by_plan["pro"] == 0


def test_get_single_user_and_unknown_user_returns_404(client, session_factory):
    token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    user_id = normal["user"]["id"]

    response = client.get(f"/api/v1/admin/users/{user_id}", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["email"] == "streamer@example.com"

    missing = client.get(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000000", headers=_auth(token)
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Usuario no encontrado."


# --- Asignación de planes -------------------------------------------------------


def test_assign_plan_updates_user_and_records_grant(client, session_factory):
    token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    user_id = normal["user"]["id"]
    expires_at = utcnow() + timedelta(days=30)

    response = client.post(
        f"/api/v1/admin/users/{user_id}/plan",
        json={
            "plan_code": "pro",
            "expires_at": expires_at.isoformat(),
            "note": "Cortesía por lanzamiento",
        },
        headers=_auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plan"]["code"] == "pro"
    assert data["plan_source"] == PLAN_SOURCE_ADMIN
    assert data["plan_expires_at"] is not None

    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "streamer@example.com"))
        pro = db.scalar(select(Plan).where(Plan.code == "pro"))
        assert user.plan_id == pro.id
        assert user.plan_source == PLAN_SOURCE_ADMIN
        grants = db.scalars(select(PlanGrant).where(PlanGrant.user_id == user.id)).all()
        assert len(grants) == 1
        assert grants[0].source == PLAN_SOURCE_ADMIN
        assert grants[0].plan_id == pro.id
        assert grants[0].granted_by is not None
        assert grants[0].note == "Cortesía por lanzamiento"


def test_assign_plan_without_expiration_leaves_it_null(client, session_factory):
    token = _admin_token(client, session_factory)
    user_id = _register(client, "streamer@example.com")["user"]["id"]

    response = client.post(
        f"/api/v1/admin/users/{user_id}/plan", json={"plan_code": "studio"}, headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["plan_expires_at"] is None


def test_assign_unknown_plan_returns_404(client, session_factory):
    token = _admin_token(client, session_factory)
    user_id = _register(client, "streamer@example.com")["user"]["id"]

    response = client.post(
        f"/api/v1/admin/users/{user_id}/plan", json={"plan_code": "inexistente"}, headers=_auth(token)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Plan no encontrado."


def test_assign_plan_with_past_expiration_returns_422(client, session_factory):
    token = _admin_token(client, session_factory)
    user_id = _register(client, "streamer@example.com")["user"]["id"]
    past = utcnow() - timedelta(days=1)

    response = client.post(
        f"/api/v1/admin/users/{user_id}/plan",
        json={"plan_code": "pro", "expires_at": past.isoformat()},
        headers=_auth(token),
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "La fecha de vencimiento debe ser futura."


def test_grants_history_lists_assignments_with_admin_email(client, session_factory):
    token = _admin_token(client, session_factory)
    user_id = _register(client, "streamer@example.com")["user"]["id"]
    client.post(
        f"/api/v1/admin/users/{user_id}/plan", json={"plan_code": "creator"}, headers=_auth(token)
    )
    client.post(
        f"/api/v1/admin/users/{user_id}/plan",
        json={"plan_code": "pro", "note": "Ascenso"},
        headers=_auth(token),
    )

    response = client.get(f"/api/v1/admin/users/{user_id}/grants", headers=_auth(token))
    assert response.status_code == 200
    grants = response.json()
    assert [grant["plan_code"] for grant in grants] == ["pro", "creator"]
    assert grants[0]["plan_name"] == "Pro"
    assert grants[0]["source"] == PLAN_SOURCE_ADMIN
    assert grants[0]["granted_by_email"] == "admin@example.com"
    assert grants[0]["note"] == "Ascenso"
    assert grants[1]["note"] is None


# --- Reglas anti-autobloqueo ----------------------------------------------------


def test_admin_cannot_remove_own_superadmin_role(client, session_factory):
    token = _admin_token(client, session_factory)
    admin_id = client.get("/api/v1/auth/me", headers=_auth(token)).json()["id"]

    response = client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"is_superadmin": False}, headers=_auth(token)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "No puedes quitarte a ti mismo los permisos de administrador."


def test_admin_cannot_deactivate_or_delete_itself(client, session_factory):
    token = _admin_token(client, session_factory)
    admin_id = client.get("/api/v1/auth/me", headers=_auth(token)).json()["id"]

    deactivate = client.patch(
        f"/api/v1/admin/users/{admin_id}", json={"is_active": False}, headers=_auth(token)
    )
    assert deactivate.status_code == 409
    assert deactivate.json()["detail"] == "No puedes desactivar tu propia cuenta."

    removal = client.delete(f"/api/v1/admin/users/{admin_id}", headers=_auth(token))
    assert removal.status_code == 409
    assert removal.json()["detail"] == "No puedes eliminar tu propia cuenta."


def test_admin_updates_and_deletes_other_users(client, session_factory):
    token = _admin_token(client, session_factory)
    user_id = _register(client, "streamer@example.com")["user"]["id"]

    patched = client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"is_active": False, "is_superadmin": True},
        headers=_auth(token),
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False
    assert patched.json()["is_superadmin"] is True

    removal = client.delete(f"/api/v1/admin/users/{user_id}", headers=_auth(token))
    assert removal.status_code == 204
    with session_factory() as db:
        assert db.scalar(select(User).where(User.email == "streamer@example.com")) is None


def test_deleting_a_user_cascades_its_grants_and_nulls_the_granter(client, session_factory):
    """Las claves foráneas están activas en los tests: se verifican las cascadas reales."""
    token = _admin_token(client, session_factory)
    otorgante = _register(client, "otorgante@example.com", "Otorgante")
    beneficiaria = _register(client, "beneficiaria@example.com", "Beneficiaria")
    _promote(session_factory, "otorgante@example.com")
    otorgante_token = _login(client, "otorgante@example.com").json()["access_token"]

    # Una asignación recibida por quien será eliminada y otra otorgada por ella.
    client.post(
        f"/api/v1/admin/users/{otorgante['user']['id']}/plan",
        json={"plan_code": "creator"},
        headers=_auth(token),
    )
    client.post(
        f"/api/v1/admin/users/{beneficiaria['user']['id']}/plan",
        json={"plan_code": "pro"},
        headers=_auth(otorgante_token),
    )

    removal = client.delete(
        f"/api/v1/admin/users/{otorgante['user']['id']}", headers=_auth(token)
    )
    assert removal.status_code == 204

    with session_factory() as db:
        otorgante_id = uuid.UUID(otorgante["user"]["id"])
        beneficiaria_id = uuid.UUID(beneficiaria["user"]["id"])
        # ON DELETE CASCADE: no quedan filas huérfanas de la cuenta eliminada.
        assert db.scalars(select(PlanGrant).where(PlanGrant.user_id == otorgante_id)).all() == []
        # ON DELETE SET NULL: la auditoría de la otra cuenta sobrevive sin otorgante.
        heredada = db.scalars(
            select(PlanGrant).where(PlanGrant.user_id == beneficiaria_id)
        ).all()
        assert len(heredada) == 1
        assert heredada[0].granted_by is None


# --- Degradación perezosa -------------------------------------------------------


def test_resolve_effective_plan_downgrades_expired_plan_and_persists(session_factory):
    with session_factory() as db:
        user = _make_user(
            db,
            "vencido@example.com",
            plan_code="pro",
            plan_source=PLAN_SOURCE_ADMIN,
            plan_expires_at=utcnow() - timedelta(days=1),
        )
        plan = resolve_effective_plan(db, user)
        assert plan.code == "free"
        assert user.plan_source == PLAN_SOURCE_SIGNUP
        assert user.plan_expires_at is None

    with session_factory() as db:
        stored = db.scalar(select(User).where(User.email == "vencido@example.com"))
        assert stored.plan.code == "free"
        assert stored.plan_source == PLAN_SOURCE_SIGNUP
        assert stored.plan_expires_at is None


def test_resolve_effective_plan_keeps_plan_that_has_not_expired(session_factory):
    with session_factory() as db:
        user = _make_user(
            db,
            "vigente@example.com",
            plan_code="pro",
            plan_source=PLAN_SOURCE_ADMIN,
            plan_expires_at=utcnow() + timedelta(days=5),
        )
        assert resolve_effective_plan(db, user).code == "pro"
        assert user.plan_source == PLAN_SOURCE_ADMIN


def test_expired_plan_is_degraded_on_the_next_authenticated_request(client, session_factory):
    token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    user_id = normal["user"]["id"]
    client.post(
        f"/api/v1/admin/users/{user_id}/plan", json={"plan_code": "pro"}, headers=_auth(token)
    )
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "streamer@example.com"))
        user.plan_expires_at = utcnow() - timedelta(minutes=1)
        db.commit()

    me = client.get("/api/v1/auth/me", headers=_auth(normal["access_token"]))
    assert me.status_code == 200
    assert me.json()["plan"]["code"] == "free"


def _create_device(client, token, name="Celular"):
    response = client.post("/api/v1/devices", json={"name": name}, headers=_auth(token))
    assert response.status_code == 200
    return response.json()


def test_expired_plan_also_clamps_the_quality_saved_in_the_devices(client, session_factory):
    """El enforcement de calidad es cooperativo: al vencer hay que recortar los settings."""
    admin_token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    client.post(
        f"/api/v1/admin/users/{normal['user']['id']}/plan",
        json={"plan_code": "pro"},
        headers=_auth(admin_token),
    )
    device = _create_device(client, normal["access_token"])
    assert device["settings"]["resolution"] == "1080p"
    assert device["settings"]["fps"] == 60

    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "streamer@example.com"))
        user.plan_expires_at = utcnow() - timedelta(minutes=1)
        db.commit()

    devices = client.get("/api/v1/devices", headers=_auth(normal["access_token"])).json()
    assert devices[0]["settings"]["resolution"] == "720p"
    assert devices[0]["settings"]["fps"] == 30


def test_assigning_a_smaller_plan_clamps_the_quality_of_the_devices(client, session_factory):
    admin_token = _admin_token(client, session_factory)
    normal = _register(client, "streamer@example.com")
    user_id = normal["user"]["id"]
    client.post(
        f"/api/v1/admin/users/{user_id}/plan", json={"plan_code": "pro"}, headers=_auth(admin_token)
    )
    _create_device(client, normal["access_token"])

    client.post(
        f"/api/v1/admin/users/{user_id}/plan",
        json={"plan_code": "free"},
        headers=_auth(admin_token),
    )
    devices = client.get("/api/v1/devices", headers=_auth(normal["access_token"])).json()
    assert devices[0]["settings"]["resolution"] == "720p"
    assert devices[0]["settings"]["fps"] == 30


# --- Bootstrap por variables de entorno -----------------------------------------


def _configure_bootstrap(monkeypatch, emails, token=BOOTSTRAP_TOKEN):
    monkeypatch.setattr(settings, "superadmin_emails", emails)
    monkeypatch.setattr(settings, "superadmin_bootstrap_token", token)


def test_ensure_bootstrap_superadmin_promotes_by_env_and_is_idempotent(
    session_factory, monkeypatch
):
    _configure_bootstrap(monkeypatch, " Jefa@Example.com , otra@example.com ")
    with session_factory() as db:
        user = _make_user(db, "jefa@example.com")
        assert ensure_bootstrap_superadmin(db, user, BOOTSTRAP_TOKEN) is True
        assert user.is_superadmin is True
        assert user.superadmin_bootstrapped_at is not None
        # Segunda llamada: sin cambios.
        assert ensure_bootstrap_superadmin(db, user, BOOTSTRAP_TOKEN) is False
        assert user.is_superadmin is True

        ajena = _make_user(db, "ajena@example.com")
        assert ensure_bootstrap_superadmin(db, ajena, BOOTSTRAP_TOKEN) is False
        assert ajena.is_superadmin is False


def test_bootstrap_requires_the_secret_even_with_the_email_listed(session_factory, monkeypatch):
    """El correo por sí solo no prueba nada: sin el secreto no hay promoción."""
    _configure_bootstrap(monkeypatch, "jefa@example.com")
    with session_factory() as db:
        user = _make_user(db, "jefa@example.com")
        assert ensure_bootstrap_superadmin(db, user, None) is False
        assert ensure_bootstrap_superadmin(db, user, "secreto-equivocado") is False
        assert user.is_superadmin is False
        assert user.superadmin_bootstrapped_at is None


def test_bootstrap_is_disabled_when_no_secret_is_configured(session_factory, monkeypatch):
    _configure_bootstrap(monkeypatch, "jefa@example.com", token="")
    with session_factory() as db:
        user = _make_user(db, "jefa@example.com")
        assert ensure_bootstrap_superadmin(db, user, "") is False
        assert user.is_superadmin is False


def test_register_and_login_apply_bootstrap_superadmin(client, monkeypatch):
    _configure_bootstrap(monkeypatch, "jefa@example.com")
    registered = _register(client, "jefa@example.com", "Jefa", bootstrap_token=BOOTSTRAP_TOKEN)
    assert registered["user"]["is_superadmin"] is True

    monkeypatch.setattr(settings, "superadmin_emails", "")
    login = _login(client, "jefa@example.com")
    # Ya promovida: el rol se conserva aunque se quite la variable de entorno.
    assert login.json()["user"]["is_superadmin"] is True


def test_registering_a_listed_email_without_the_secret_grants_nothing(client, monkeypatch):
    """Regresión: quien se adelante a registrar el correo del dueño no gana privilegios."""
    _configure_bootstrap(monkeypatch, "jefa@example.com")
    usurpador = _register(client, "jefa@example.com", "Impostor")
    assert usurpador["user"]["is_superadmin"] is False

    # Tampoco al volver a entrar, ni probando secretos al azar.
    login = _login(client, "jefa@example.com", bootstrap_token="secreto-equivocado")
    assert login.json()["user"]["is_superadmin"] is False


def test_login_promotes_an_existing_account(client, monkeypatch):
    _register(client, "tardia@example.com", "Tardía")
    _configure_bootstrap(monkeypatch, "tardia@example.com")
    login = _login(client, "tardia@example.com", bootstrap_token=BOOTSTRAP_TOKEN)
    assert login.status_code == 200
    assert login.json()["user"]["is_superadmin"] is True


def test_revoked_superadmin_is_not_restored_by_the_bootstrap(client, session_factory, monkeypatch):
    """La revocación desde el panel manda sobre la variable de entorno."""
    _configure_bootstrap(monkeypatch, "socio@example.com")
    admin_token = _admin_token(client, session_factory)
    socio = _register(client, "socio@example.com", "Socio", bootstrap_token=BOOTSTRAP_TOKEN)
    assert socio["user"]["is_superadmin"] is True

    revoked = client.patch(
        f"/api/v1/admin/users/{socio['user']['id']}",
        json={"is_superadmin": False},
        headers=_auth(admin_token),
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_superadmin"] is False

    # Vuelve a entrar con el secreto y el correo todavía en la variable: sigue sin rol.
    login = _login(client, "socio@example.com", bootstrap_token=BOOTSTRAP_TOKEN)
    assert login.status_code == 200
    assert login.json()["user"]["is_superadmin"] is False

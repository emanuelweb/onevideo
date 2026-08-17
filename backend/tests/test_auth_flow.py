REGISTER_BODY = {
    "email": "streamer@example.com",
    "password": "clave-segura-123",
    "name": "Streamer LATAM",
}


def _register(client, body=None):
    return client.post("/api/v1/auth/register", json=body or REGISTER_BODY)


def test_register_returns_token_and_user(client):
    response = _register(client)
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == REGISTER_BODY["email"]
    assert data["user"]["name"] == REGISTER_BODY["name"]
    assert data["user"]["plan"]["code"] == "free"
    assert data["user"]["plan"]["monthly_hours"] == 15


def test_register_normalizes_email_and_rejects_duplicates(client):
    assert _register(client).status_code == 200
    duplicate = _register(
        client, {**REGISTER_BODY, "email": "STREAMER@example.com"}
    )
    assert duplicate.status_code == 409
    assert isinstance(duplicate.json()["detail"], str)


def test_register_invalid_email_returns_422_spanish_detail(client):
    response = _register(client, {**REGISTER_BODY, "email": "no-es-un-correo"})
    assert response.status_code == 422
    assert "inválidos" in response.json()["detail"]


def test_login_ok(client):
    _register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_BODY["email"], "password": REGISTER_BODY["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["user"]["email"] == REGISTER_BODY["email"]


def test_login_wrong_password(client):
    _register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_BODY["email"], "password": "clave-incorrecta"},
    )
    assert response.status_code == 401
    assert isinstance(response.json()["detail"], str)


def test_me_requires_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_with_invalid_token(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer token-invalido"}
    )
    assert response.status_code == 401


def test_me_returns_current_user(client):
    token = _register(client).json()["access_token"]
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == REGISTER_BODY["email"]
    assert data["plan"]["code"] == "free"

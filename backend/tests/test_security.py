from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    password = "clave-súper-segura-123"
    password_hash = hash_password(password)
    assert password_hash != password
    assert password_hash.startswith("$2b$12$")
    assert verify_password(password, password_hash) is True
    assert verify_password("otra-clave", password_hash) is False


def test_verify_password_with_malformed_hash():
    assert verify_password("cualquiera", "no-es-un-hash-bcrypt") is False


def test_hashes_are_salted():
    assert hash_password("misma-clave-123") != hash_password("misma-clave-123")


def test_jwt_roundtrip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_jwt_tampered_is_rejected():
    token = create_access_token("user-123")
    assert decode_access_token(token + "x") is None
    assert decode_access_token("token.invalido.total") is None


def test_jwt_expired_is_rejected():
    token = create_access_token("user-123", expires_minutes=-5)
    assert decode_access_token(token) is None

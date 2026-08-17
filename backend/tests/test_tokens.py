import re

from app.security import (
    PAIRING_CODE_LENGTH,
    constant_time_equals,
    generate_opaque_token,
    generate_pairing_code,
    sha256_hex,
)


def test_pairing_code_format():
    for _ in range(50):
        code = generate_pairing_code()
        assert len(code) == PAIRING_CODE_LENGTH
        assert re.fullmatch(r"[A-Z0-9]{8}", code)


def test_opaque_token_format():
    token = generate_opaque_token()
    # secrets.token_urlsafe(32) -> 43 caracteres urlsafe.
    assert len(token) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)


def test_opaque_tokens_are_unique():
    tokens = {generate_opaque_token() for _ in range(100)}
    assert len(tokens) == 100


def test_sha256_hex():
    digest = sha256_hex("hola")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == sha256_hex("hola")
    assert digest != sha256_hex("chau")


def test_constant_time_equals():
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False
    assert constant_time_equals("abc", "abcd") is False

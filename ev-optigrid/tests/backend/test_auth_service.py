import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest


def test_hash_password_not_plaintext():
    from services.auth_service import hash_password
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$2b$")  # bcrypt prefix


def test_verify_password_correct():
    from services.auth_service import hash_password, verify_password
    hashed = hash_password("my-secret-password")
    assert verify_password("my-secret-password", hashed)


def test_verify_password_incorrect():
    from services.auth_service import hash_password, verify_password
    hashed = hash_password("my-secret-password")
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    from services.auth_service import create_access_token, decode_token
    token = create_access_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    from services.auth_service import create_refresh_token, decode_token
    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"


def test_different_passwords_produce_different_hashes():
    from services.auth_service import hash_password
    assert hash_password("password1") != hash_password("password2")


def test_same_password_produces_different_hash_due_to_salt():
    from services.auth_service import hash_password
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2  # bcrypt salts each hash uniquely

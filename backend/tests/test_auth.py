import pytest
from fastapi.testclient import TestClient

from app import auth, config
from app.db import init_db
from app.main import app


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "auth-test.db"))
    init_db()
    sent_codes = []
    monkeypatch.setattr(
        auth.notifier,
        "send_auth_code",
        lambda phone, code, purpose: sent_codes.append((phone, code, purpose)) or "mock",
    )
    return TestClient(app), sent_codes


def test_signup_phone_verification_and_password_reset(auth_client):
    client, sent_codes = auth_client
    phone = "+919876543210"

    response = client.post(
        "/api/auth/signup",
        json={"name": "Test Patient", "phone": phone, "password": "start-password"},
    )
    assert response.status_code == 200
    assert sent_codes[-1][2] == "signup"

    response = client.post(
        "/api/auth/verify-phone",
        json={"phone": phone, "code": sent_codes[-1][1]},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    profile = response.json()["profile"]
    assert profile["phone"] == phone
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get(f"/api/profiles/{profile['id']}", headers=headers).status_code == 200
    assert client.get("/api/profiles/another-profile", headers=headers).status_code == 404

    response = client.post("/api/auth/forgot-password", json={"phone": phone})
    assert response.status_code == 200
    assert sent_codes[-1][2] == "reset"
    response = client.post(
        "/api/auth/reset-password",
        json={"phone": phone, "code": sent_codes[-1][1], "new_password": "updated-password"},
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"phone": phone, "password": "start-password"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"phone": phone, "password": "updated-password"},
    ).status_code == 200


def test_invalid_verification_codes_are_counted(auth_client):
    client, sent_codes = auth_client
    phone = "+919876543211"
    client.post("/api/auth/signup", json={"phone": phone, "password": "start-password"})
    wrong_code = "000000" if sent_codes[-1][1] != "000000" else "000001"

    for _ in range(5):
        response = client.post("/api/auth/verify-phone", json={"phone": phone, "code": wrong_code})
        assert response.status_code == 400
    response = client.post(
        "/api/auth/verify-phone",
        json={"phone": phone, "code": sent_codes[-1][1]},
    )
    assert response.status_code == 400

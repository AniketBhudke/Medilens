from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import auth, config, main
from app.db import get_db, init_db
from app.services.schedule import iso


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "chat-test.db"))
    init_db()
    codes = []
    monkeypatch.setattr(auth.notifier, "send_auth_code", lambda phone, code, purpose: codes.append(code) or "mock")
    client = TestClient(main.app)
    phone = "+919876543213"
    client.post("/api/auth/signup", json={"phone": phone, "password": "start-password"})
    session = client.post(
        "/api/auth/verify-phone",
        json={"phone": phone, "code": codes[-1]},
    ).json()
    return client, session["profile"]["id"], {"Authorization": f"Bearer {session['token']}"}


def test_chat_uses_labeled_demo_data_without_anthropic_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "anthropic_api_key", "")
    client, _, headers = _client(tmp_path, monkeypatch)

    question = {"messages": [{"role": "user", "content": "give me tablet usecase"}]}
    assert client.post("/api/chat", json=question).status_code == 401
    response = client.post("/api/chat", headers=headers, json=question)
    assert response.status_code == 200
    assert response.json()["demo"] is True
    assert "Tab Dolo 650" in response.json()["answer"]
    assert "fever and pain" in response.json()["answer"]


def test_demo_chat_does_not_invent_unknown_medicine_information(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "anthropic_api_key", "")
    client, profile_id, headers = _client(tmp_path, monkeypatch)
    now = iso(datetime.now(timezone.utc))
    with get_db() as db:
        db.execute(
            "INSERT INTO medication_courses (id, profile_id, med_name, strength, planned_doses, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("course-unknown", profile_id, "Unknown medicine", "", 1, now),
        )
        db.execute(
            "INSERT INTO doses (profile_id, course_id, med_name, slot, scheduled_at) VALUES (?, ?, ?, ?, ?)",
            (profile_id, "course-unknown", "Unknown medicine", "morning", now),
        )

    response = client.post(
        "/api/chat",
        headers=headers,
        json={"messages": [{"role": "user", "content": "What is this tablet used for?"}]},
    )
    assert response.status_code == 200
    assert response.json()["demo"] is True
    assert "no sample information" in response.json()["answer"]


def test_chat_uses_only_signed_in_profile_medicine_context(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "anthropic_api_key", "test-key")
    client, profile_id, headers = _client(tmp_path, monkeypatch)
    now = iso(datetime.now(timezone.utc))
    with get_db() as db:
        db.execute(
            "INSERT INTO medication_courses (id, profile_id, med_name, strength, planned_doses, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("course-chat", profile_id, "Example tablet", "10 mg", 1, now),
        )
        db.execute(
            "INSERT INTO doses (profile_id, course_id, med_name, strength, slot, instructions, scheduled_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (profile_id, "course-chat", "Example tablet", "10 mg", "morning", "Take after food", now),
        )

    import anthropic

    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="It is generally used for…")])

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"messages": [
            {"role": "user", "content": "What is this tablet?"},
            {"role": "assistant", "content": "Which one?"},
            {"role": "user", "content": "Example tablet"},
        ]},
    )
    assert response.status_code == 200
    assert response.json()["demo"] is False
    assert response.json()["answer"] == "It is generally used for…"
    assert "Example tablet" in captured["system"]
    assert "Take after food" in captured["system"]

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import auth, config, main
from app.db import get_db, init_db
from app.services import notifier
from app.services.schedule import iso
from app.services.scheduler import tick


def test_course_sms_waits_for_every_dose_and_sends_once(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "course-test.db"))
    init_db()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    course_id = "course-123"
    with get_db() as db:
        db.execute(
            "INSERT INTO profiles (id, name, phone, created_at) VALUES (?, ?, ?, ?)",
            ("profile-123", "Test Patient", "+919876543210", iso(now)),
        )
        db.execute(
            "INSERT INTO medication_courses (id, profile_id, med_name, strength, planned_doses, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (course_id, "profile-123", "Test tablet", "10 mg", 2, iso(now)),
        )
        for status in ("taken", "pending"):
            db.execute(
                "INSERT INTO doses (profile_id, course_id, med_name, strength, slot, scheduled_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("profile-123", course_id, "Test tablet", "10 mg", "morning", iso(now), status),
            )

    sent = []
    monkeypatch.setattr(
        notifier,
        "send_course_completion_sms",
        lambda phone, meds, language: sent.append((phone, meds, language)) or "mock",
    )
    assert tick(now)["completed"] == 0
    assert sent == []

    with get_db() as db:
        db.execute("UPDATE doses SET status='taken' WHERE course_id=?", (course_id,))
    assert tick(now)["completed"] == 1
    assert sent == [("+919876543210", "Test tablet 10 mg", "en")]
    assert tick(now)["completed"] == 0
    assert len(sent) == 1


def test_five_day_prescription_creates_five_doses_and_confirmation_closes_alarm(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "db_path", str(tmp_path / "five-days-test.db"))
    init_db()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
            return fixed if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(main, "datetime", FixedDateTime)
    codes = []
    monkeypatch.setattr(auth.notifier, "send_auth_code", lambda phone, code, purpose: codes.append(code) or "mock")
    client = TestClient(main.app)
    phone = "+919876543212"
    client.post("/api/auth/signup", json={"phone": phone, "password": "start-password"})
    verified = client.post("/api/auth/verify-phone", json={"phone": phone, "code": codes[-1]})
    token = verified.json()["token"]
    profile_id = verified.json()["profile"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        f"/api/profiles/{profile_id}/plan",
        headers=headers,
        json={
            "medicines": [
                {"name": "Test tablet", "frequency_raw": "OD", "duration_days": 5},
                {"name": "Unclear duration", "frequency_raw": "OD"},
            ],
            "replace_existing": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["created"] == 5
    assert response.json()["skipped"] == [{
        "name": "Unclear duration",
        "reason": "course duration not stated; confirm it before scheduling",
    }]

    with get_db() as db:
        doses = db.execute("SELECT id FROM doses WHERE profile_id=? ORDER BY scheduled_at", (profile_id,)).fetchall()
    assert len(doses) == 5
    response = client.post(f"/api/doses/{doses[0]['id']}/confirm", headers=headers)
    assert response.status_code == 404
    with get_db() as db:
        db.execute(
            "UPDATE doses SET status='alarming', alarm_at=? WHERE id=?",
            (iso(datetime(2026, 1, 1, 2, 30, tzinfo=timezone.utc)), doses[0]["id"]),
        )
    active = client.get(f"/api/profiles/{profile_id}/alarms", headers=headers).json()["alarms"]
    assert [alarm["id"] for alarm in active] == [doses[0]["id"]]
    response = client.post(f"/api/doses/{doses[0]['id']}/confirm", headers=headers)
    assert response.status_code == 200
    assert client.get(f"/api/profiles/{profile_id}/alarms", headers=headers).json()["alarms"] == []
    with get_db() as db:
        status = db.execute("SELECT status FROM doses WHERE id=?", (doses[0]["id"],)).fetchone()["status"]
    assert status == "taken"

from datetime import datetime, timezone

from app.services import interactions, labs, schedule


def test_parse_101():
    assert schedule.parse_frequency("1-0-1")["slots"] == {"morning": 1.0, "night": 1.0}

def test_parse_abbrev():
    assert schedule.parse_frequency("BD")["slots"] == {"morning": 1.0, "night": 1.0}
    assert schedule.parse_frequency("TDS")["slots"] == {"morning": 1, "afternoon": 1, "night": 1}
    assert schedule.parse_frequency("HS")["slots"] == {"night": 1}
    assert set(schedule.parse_frequency("QID")["slots"]) == {"morning", "afternoon", "evening", "night"}

def test_sos():
    r = schedule.parse_frequency("SOS")
    assert r["as_needed"] and not r["slots"]

def test_four_part():
    assert set(schedule.parse_frequency("1-1-1-1")["slots"]) == {"morning", "afternoon", "evening", "night"}

def test_unparseable():
    assert schedule.parse_frequency("as directed") == {"slots": {}, "as_needed": False}

def test_duration():
    assert schedule.parse_duration_days("2 weeks") == 14
    assert schedule.parse_duration_days("5 days") == 5
    assert schedule.parse_duration_days(None) is None

def test_dose_times_timezone():
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)  # 05:30 IST
    times = {"morning": "08:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00"}
    out = list(schedule.build_dose_times({"morning": 1}, 2, datetime(2026, 1, 1).date(), times, "Asia/Kolkata", now))
    assert len(out) == 2
    assert out[0][2].hour == 2 and out[0][2].minute == 30  # 08:00 IST = 02:30 UTC

def test_five_day_course_schedules_five_daily_doses():
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    times = {"morning": "08:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00"}
    out = list(schedule.build_dose_times({"morning": 1}, 5, datetime(2026, 1, 1).date(), times, "Asia/Kolkata", now))
    assert len(out) == 5

def test_lab_flags():
    r = labs.evaluate([{"test": "Hb", "value": 10.2}, {"test": "FBS", "value": 90}, {"test": "Mystery", "value": 5}], "female")
    assert r[0]["flag"] == "low" and r[1]["flag"] == "normal" and r[2]["flag"] == "unknown"

def test_duplicate_via_brand():
    meds = [{"name": "Dolo 650"}, {"name": "Crocin"}]
    assert interactions.find_duplicates(meds)

def test_interaction():
    meds = [{"name": "Ecosprin", "active_ingredient": "aspirin"}, {"name": "Warf", "active_ingredient": "warfarin"}]
    assert interactions.check_interactions(meds)[0]["severity"] == "high"

def test_no_false_positive():
    assert not interactions.all_warnings([{"name": "Pan 40", "active_ingredient": "pantoprazole"}, {"name": "Dolo", "active_ingredient": "paracetamol"}])

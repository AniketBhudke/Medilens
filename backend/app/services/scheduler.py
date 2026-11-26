"""Escalation engine, run every 20 seconds:
   pending --(time reached)--> alarming --(+escalation_min)--> voice/missed call
           --(+caregiver_min)--> caregiver SMS --(+30 min)--> missed
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..db import get_db
from . import notifier
from .schedule import iso, parse_iso

log = logging.getLogger("medlens.scheduler")
STALE_AFTER = timedelta(hours=2)   # server was down: don't alarm for ancient doses
MISSED_GRACE = timedelta(minutes=30)


def tick(now: datetime | None = None, profile_id: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    stats = {"alarms": 0, "calls": 0, "caregiver": 0, "missed": 0, "completed": 0}
    with get_db() as db:
        # 1) fire alarms
        pending_sql = "SELECT * FROM doses WHERE status='pending' AND scheduled_at<=?"
        pending_args = [iso(now)]
        if profile_id:
            pending_sql += " AND profile_id=?"
            pending_args.append(profile_id)
        for d in db.execute(pending_sql, pending_args).fetchall():
            if now - parse_iso(d["scheduled_at"]) > STALE_AFTER:
                db.execute("UPDATE doses SET status='missed' WHERE id=?", (d["id"],))
                stats["missed"] += 1
            else:
                db.execute("UPDATE doses SET status='alarming', alarm_at=? WHERE id=?", (iso(now), d["id"]))
                stats["alarms"] += 1

        # 2) escalate alarming doses. Doses due together are grouped into ONE call per profile.
        active_sql = (
            "SELECT d.*, p.name AS pname, p.phone, p.caregiver_phone, p.language, p.tz, p.escalation_min, p.caregiver_min "
            "FROM doses d JOIN profiles p ON p.id=d.profile_id WHERE d.status='alarming'"
        )
        active_args = []
        if profile_id:
            active_sql += " AND d.profile_id=?"
            active_args.append(profile_id)
        rows = db.execute(active_sql, active_args).fetchall()
        call_groups, cg_groups = {}, {}
        for d in rows:
            alarm_at = parse_iso(d["alarm_at"])
            if d["call_at"] is None:
                if now >= alarm_at + timedelta(minutes=d["escalation_min"]):
                    call_groups.setdefault(d["profile_id"], []).append(d)
            else:
                call_at = parse_iso(d["call_at"])
                if d["caregiver_at"] is None and now >= call_at + timedelta(minutes=d["caregiver_min"]):
                    cg_groups.setdefault(d["profile_id"], []).append(d)
                limit = (parse_iso(d["caregiver_at"]) if d["caregiver_at"] else call_at + timedelta(minutes=d["caregiver_min"])) + MISSED_GRACE
                if now >= limit:
                    db.execute("UPDATE doses SET status='missed' WHERE id=?", (d["id"],))
                    stats["missed"] += 1

        for pid, doses in call_groups.items():
            p = doses[0]
            meds = ", ".join(dict.fromkeys(f"{x['med_name']} {x['strength']}".strip() for x in doses))
            try:
                sid, status = notifier.place_reminder_call(p["phone"], p["pname"], meds, p["language"])
            except Exception as e:  # never let a Twilio error kill the loop
                log.exception("call failed")
                sid, status = "", f"error: {e}"[:200]
            for x in doses:
                db.execute("UPDATE doses SET call_at=?, call_sid=?, call_status=? WHERE id=?", (iso(now), sid, status, x["id"]))
            stats["calls"] += 1

        for pid, doses in cg_groups.items():
            p = doses[0]
            if not p["caregiver_phone"]:
                continue
            meds = ", ".join(dict.fromkeys(x["med_name"] for x in doses))
            local = parse_iso(doses[0]["scheduled_at"]).astimezone(ZoneInfo(p["tz"])).strftime("%I:%M %p")
            try:
                notifier.send_caregiver_sms(p["caregiver_phone"], p["pname"], meds, local, p["language"])
            except Exception:
                log.exception("caregiver sms failed")
            for x in doses:
                db.execute("UPDATE doses SET caregiver_at=? WHERE id=?", (iso(now), x["id"]))
            stats["caregiver"] += 1

        courses_sql = (
            "SELECT c.*, p.phone, p.language FROM medication_courses c "
            "JOIN profiles p ON p.id=c.profile_id "
            "WHERE c.completion_notified_at IS NULL "
            "AND EXISTS (SELECT 1 FROM doses d WHERE d.course_id=c.id) "
            "AND NOT EXISTS (SELECT 1 FROM doses d WHERE d.course_id=c.id AND d.status!='taken')"
        )
        courses_args = []
        if profile_id:
            courses_sql += " AND c.profile_id=?"
            courses_args.append(profile_id)
        courses = db.execute(courses_sql, courses_args).fetchall()
        for course in courses:
            if not course["phone"]:
                continue
            meds = f"{course['med_name']} {course['strength']}".strip()
            try:
                status = notifier.send_course_completion_sms(course["phone"], meds, course["language"])
            except Exception:
                log.exception("course completion SMS failed")
                continue
            if status != "no_phone":
                db.execute(
                    "UPDATE medication_courses SET completion_notified_at=?, completion_status=? "
                    "WHERE id=? AND completion_notified_at IS NULL",
                    (iso(now), status, course["id"]),
                )
                stats["completed"] += 1
    return stats

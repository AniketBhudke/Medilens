import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .auth import current_account, router as auth_router
from .config import settings
from .db import get_db, init_db
from .schemas import ChatIn, PlanIn, ProfileIn
from .services import ai_agent, chat, interactions, labs, ocr, schedule
from .services.scheduler import tick

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("medlens")

sched = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sched.add_job(tick, "interval", seconds=20, id="tick", max_instances=1, coalesce=True)
    sched.start()
    log.info("MedLens started | AI=%s | Twilio=%s", "live" if settings.anthropic_api_key else "DEMO", "live" if settings.twilio_ready else "MOCK")
    yield
    sched.shutdown(wait=False)


app = FastAPI(title="MedLens API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"}


@app.get("/api/health")
def health():
    return {"ok": True, "ai": "live" if settings.anthropic_api_key else "demo", "calls": "live" if settings.twilio_ready else "mock", "demo_mode": settings.demo_mode}


# ---------------------------------------------------------------- analyze
@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...), language: str = Form("en"), sex: str = Form("unknown"),
    force: bool = Form(False), account: dict = Depends(current_account),
):
    """Upload photo/PDF -> quality guardrail -> AI agent -> deterministic safety checks."""
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {settings.max_upload_mb} MB).")
    ctype = file.content_type or ""
    if ctype not in ALLOWED:
        raise HTTPException(415, "Upload a JPG/PNG photo or a PDF.")
    if language not in ("en", "hi", "mr"):
        language = "en"

    quality, hint = None, ""
    if ctype == "application/pdf":
        media_type = ctype
    else:
        try:
            data, quality = ocr.assess_and_prepare(data)
        except Exception:
            raise HTTPException(422, "Could not read this image. Try another photo.")
        media_type = "image/jpeg"
        if quality["is_poor"] and not force:
            return {"status": "needs_reupload", "quality": quality,
                    "message": "This photo is not clear enough to read safely. Please retake it in good light, hold the phone steady, and fill the frame with the paper. Or show it to your pharmacist or doctor."}
        hint = ocr.optional_ocr_text(data)

    try:
        report = ai_agent.analyze_document(data, media_type, language, sex if sex in ("male", "female") else None, hint)
    except Exception as e:
        log.exception("analysis failed")
        raise HTTPException(502, f"AI analysis failed: {e}")

    meds = report.get("medicines", [])
    for m in meds:
        p = schedule.parse_frequency(m.get("frequency_raw"))
        m["parsed_slots"] = p["slots"]
        m["as_needed"] = p["as_needed"]
        m["schedulable"] = bool(p["slots"])
        m["low_confidence"] = float(m.get("confidence", 1)) < 0.6
        m["duration_days"] = schedule.parse_duration_days(m.get("duration_days"))
    lab_rows = labs.evaluate(report.get("lab_results", []), sex if sex in ("male", "female") else None)
    warnings = interactions.all_warnings(meds)

    conf = float(report.get("overall_confidence", 0))
    low = conf < 0.65 or any(m["low_confidence"] for m in meds) or bool((quality or {}).get("is_poor"))
    return {
        "status": "needs_verification" if low else "ok",
        "document_type": report.get("document_type", "unknown"),
        "overall_confidence": conf,
        "legibility_issues": report.get("legibility_issues", []) + (quality or {}).get("issues", []),
        "doctor_or_clinic": report.get("doctor_or_clinic", ""),
        "summary": report.get("summary", ""),
        "medicines": meds,
        "lab_results": lab_rows,
        "abnormal_count": sum(1 for r in lab_rows if r["flag"] in ("low", "high")),
        "warnings": warnings,
        "quality": quality,
        "demo": not settings.anthropic_api_key,
        "disclaimer": "MedLens explains documents; it does not replace your doctor or pharmacist. Verify medicines and doses with them.",
    }


@app.post("/api/chat")
def medication_chat(body: ChatIn, account: dict = Depends(current_account)):
    with get_db() as db:
        profile = _profile(db, account["profile_id"], account)
        rows = db.execute(
            "SELECT c.med_name, c.strength, "
            "group_concat(DISTINCT d.slot || ' x ' || d.quantity) AS planned_slots, "
            "group_concat(DISTINCT NULLIF(d.instructions, '')) AS instructions, "
            "CASE WHEN NOT EXISTS (SELECT 1 FROM doses d2 WHERE d2.course_id=c.id AND d2.status!='taken') "
            "THEN 'all planned doses confirmed taken' ELSE 'course not fully confirmed' END AS course_status "
            "FROM medication_courses c JOIN doses d ON d.course_id=c.id "
            "WHERE c.profile_id=? GROUP BY c.id ORDER BY c.created_at DESC LIMIT 20",
            (profile["id"],),
        ).fetchall()
    medication_context = [dict(row) for row in rows]
    if not settings.anthropic_api_key:
        return {
            "answer": chat.answer_demo_chat(body.messages, medication_context, profile["language"]),
            "demo": True,
        }
    try:
        answer = chat.answer_chat(body.messages, medication_context, profile["language"])
    except chat.ChatProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"answer": answer, "demo": False}


# ---------------------------------------------------------------- profiles
def _profile(db, pid, account):
    if pid != account["profile_id"]:
        raise HTTPException(404, "Profile not found")
    row = db.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Profile not found")
    return row


@app.post("/api/profiles")
def create_profile(account: dict = Depends(current_account)):
    raise HTTPException(409, "A profile is created when you sign up.")


@app.get("/api/profiles/{pid}")
def get_profile(pid: str, account: dict = Depends(current_account)):
    with get_db() as db:
        return dict(_profile(db, pid, account))


@app.put("/api/profiles/{pid}")
def update_profile(pid: str, body: ProfileIn, account: dict = Depends(current_account)):
    with get_db() as db:
        _profile(db, pid, account)
        if body.phone != account["phone"]:
            raise HTTPException(400, "The sign-in phone number cannot be changed in profile settings.")
        cols = body.model_dump()
        db.execute(f"UPDATE profiles SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", (*cols.values(), pid))
        return dict(_profile(db, pid, account))


# ---------------------------------------------------------------- plan & doses
@app.post("/api/profiles/{pid}/plan")
def create_plan(pid: str, body: PlanIn, account: dict = Depends(current_account)):
    now = datetime.now(timezone.utc)
    created, skipped = 0, []
    with get_db() as db:
        p = _profile(db, pid, account)
        times = {"morning": p["t_morning"], "afternoon": p["t_afternoon"], "evening": p["t_evening"], "night": p["t_night"]}
        start_day = now.astimezone(ZoneInfo(p["tz"])).date()
        if body.replace_existing:
            db.execute(
                "DELETE FROM medication_courses WHERE id IN "
                "(SELECT course_id FROM doses WHERE profile_id=? AND status IN ('pending','alarming'))",
                (pid,),
            )
            db.execute("DELETE FROM doses WHERE profile_id=? AND status IN ('pending','alarming')", (pid,))
        for m in body.medicines:
            parsed = schedule.parse_frequency(m.frequency_raw)
            slots = schedule.slots_from_dict(m.slots) or parsed["slots"]
            if not slots:
                skipped.append({"name": m.name, "reason": "as needed (SOS)" if parsed["as_needed"] else "could not read timing"})
                continue
            days = m.duration_days if m.duration_days is not None else body.default_days
            if days is None:
                skipped.append({"name": m.name, "reason": "course duration not stated; confirm it before scheduling"})
                continue
            instr = m.how_to_take or {"before_food": "Take before food", "after_food": "Take after food", "with_food": "Take with food", "empty_stomach": "Take on an empty stomach"}.get(m.food_timing, "")
            dose_times = list(schedule.build_dose_times(slots, min(days, 60), start_day, times, p["tz"], now))
            if not dose_times:
                skipped.append({"name": m.name, "reason": "no future doses in this course"})
                continue
            course_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO medication_courses (id, profile_id, med_name, strength, planned_doses, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (course_id, pid, m.name, m.strength, len(dose_times), schedule.iso(now)),
            )
            for slot, qty, when in dose_times:
                db.execute(
                    "INSERT INTO doses (profile_id, course_id, med_name, strength, quantity, slot, food_timing, instructions, scheduled_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, course_id, m.name, m.strength, qty, slot, m.food_timing, instr, schedule.iso(when)),
                )
                created += 1
    return {"created": created, "skipped": skipped}


@app.get("/api/profiles/{pid}/schedule")
def day_schedule(pid: str, date: str | None = None, account: dict = Depends(current_account)):
    """Doses for one local day (default today), grouped by slot."""
    with get_db() as db:
        p = _profile(db, pid, account)
        tz = ZoneInfo(p["tz"])
        day = datetime.fromisoformat(date).date() if date else datetime.now(tz).date()
        start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc)
        end = start + timedelta(days=1)
        rows = db.execute("SELECT * FROM doses WHERE profile_id=? AND scheduled_at>=? AND scheduled_at<? ORDER BY scheduled_at",
                          (pid, schedule.iso(start), schedule.iso(end))).fetchall()
    out = {"morning": [], "afternoon": [], "evening": [], "night": []}
    for r in rows:
        d = dict(r)
        d["time_local"] = schedule.parse_iso(r["scheduled_at"]).astimezone(tz).strftime("%I:%M %p")
        out[r["slot"]].append(d)
    total = len(rows)
    taken = sum(1 for r in rows if r["status"] == "taken")
    return {"date": day.isoformat(), "slots": out, "total": total, "taken": taken}


@app.get("/api/profiles/{pid}/alarms")
def active_alarms(pid: str, account: dict = Depends(current_account)):
    """Polled by the web app: doses whose alarm should be ringing right now."""
    with get_db() as db:
        p = _profile(db, pid, account)
        tz = ZoneInfo(p["tz"])
        rows = db.execute("SELECT * FROM doses WHERE profile_id=? AND status='alarming' ORDER BY scheduled_at", (pid,)).fetchall()
    res = []
    for r in rows:
        d = dict(r)
        d["time_local"] = schedule.parse_iso(r["scheduled_at"]).astimezone(tz).strftime("%I:%M %p")
        res.append(d)
    return {"alarms": res}


@app.post("/api/doses/{dose_id}/confirm")
def confirm(dose_id: int, account: dict = Depends(current_account)):
    now = schedule.iso(datetime.now(timezone.utc))
    with get_db() as db:
        cur = db.execute(
            "UPDATE doses SET status='taken', taken_at=? WHERE id=? AND profile_id=? "
            "AND (status IN ('alarming','missed') OR (status='pending' AND scheduled_at<=?))",
            (now, dose_id, account["profile_id"], now),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Dose not found or already confirmed")
    return {"ok": True}


@app.post("/api/doses/{dose_id}/fire")
def fire_now(dose_id: int, account: dict = Depends(current_account)):
    """DEMO helper: make a dose due right now so you can see the alarm + escalation."""
    if not settings.demo_mode:
        raise HTTPException(403, "Disabled outside demo mode")
    with get_db() as db:
        cur = db.execute(
            "UPDATE doses SET status='pending', scheduled_at=?, alarm_at=NULL, call_at=NULL, caregiver_at=NULL "
            "WHERE id=? AND profile_id=? AND status!='taken'",
            (schedule.iso(datetime.now(timezone.utc) - timedelta(seconds=1)), dose_id, account["profile_id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Dose not found or already taken")
    tick(profile_id=account["profile_id"])
    return {"ok": True}


@app.post("/api/dev/tick")
def dev_tick(account: dict = Depends(current_account)):
    if not settings.demo_mode:
        raise HTTPException(403, "Disabled outside demo mode")
    return tick(profile_id=account["profile_id"])


@app.post("/api/webhooks/twilio/status")
async def twilio_status(request: Request):
    form = await request.form()
    sid, status = form.get("CallSid"), form.get("CallStatus")
    if sid and status:
        with get_db() as db:
            db.execute("UPDATE doses SET call_status=? WHERE call_sid=?", (status, sid))
    return {"ok": True}

# MedLens — AI Prescription Interpreter & Voice-Call Medication Reminder

Upload a photo/PDF of a prescription or lab report → an AI agent reads it, explains it in simple English / Hindi / Marathi,
flags abnormal lab values, warns about duplicate/clashing medicines, builds a Morning/Afternoon/Night timetable, rings a
full-screen alarm in the app and — if you don't tap **I took it** — places an automated voice (or missed) call, then
alerts a caregiver by SMS.

**Stack:** React (Vite) · Python FastAPI REST API · SQLite · APScheduler · Claude (multimodal + tool-use agent) · Twilio (voice/SMS)

## Run it

### 1. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # add keys (optional, see below)
uvicorn app.main:app --reload --port 8000
```
Swagger docs: http://localhost:8000/docs

### Accounts and medication courses
- Create an account with a phone number in international format (`+91…`) and a password. Verify the phone with the SMS code before signing in.
- **Forgot password** sends a reset code to the registered mobile. Codes expire after 10 minutes. With Twilio credentials blank, SMS is mocked and the code is printed in the backend console for local testing.
- Passwords are stored as salted PBKDF2 hashes; sign-in sessions expire after 30 days. Use HTTPS and deployment-grade secrets before exposing the app publicly.
- After scanning a prescription, review/confirm each course length (for example, five days) before creating reminders. If the duration cannot be read, enter it from the prescription or confirm it with a clinician; the app does not guess. Each dose has its own alarm; tapping **I took it** dismisses that alarm.
- A course-completion SMS is sent to the registered phone only after every scheduled dose in that medicine's course is marked **Taken**. Missed or unconfirmed doses do not produce a completion message.
- **Ask MedLens** answers general medicine-use and prescription questions using the configured Anthropic model and the signed-in profile's medication list. Chat history stays in browser memory and is not saved by the server; answers are informational, not personalized medical advice. Without `ANTHROPIC_API_KEY`, it only gives clearly labeled sample-use information for bundled demo medicines and declines unknown-medication questions.

### 2. Frontend
```bash
cd frontend
npm install
npm run dev                                             # http://localhost:5173
```

### No keys? Still works
- No `ANTHROPIC_API_KEY` → returns **demo** prescription + lab data so you can try the full flow.
- No Twilio keys → calls/SMS are **mocked** (printed in the backend log).
- No `ANTHROPIC_API_KEY` → medication chat is limited to sample medicine uses; configure a key for open-ended questions.

### Demo the escalation in 1 minute
1. Sign up with your phone (`+91…`) and password, then enter the verification code shown in backend logs when SMS is mocked.
2. Scan tab → pick a file → *Read my document* → *Create reminders*.
3. Settings → add a caregiver phone; set both waits to 1 minute.
4. Today tab → **Test alarm now** on any dose. Full-screen alarm rings.
5. Don't tap anything: after 1 min the voice call is placed, after 1 more min the caregiver gets an SMS.
   (Use authenticated `POST /api/dev/tick` to force the scheduler for your account.)

## Architecture
```
React PWA ──REST──> FastAPI
                     ├─ /api/analyze ── quality guardrail (blur/dark/low-res)
                     │                └─ AI agent loop (Claude, tools below)
                     │                     ├ check_drug_interactions   (data/interactions.json)
                     │                     ├ find_duplicate_ingredients (data/brand_salts.json)
                     │                     ├ evaluate_lab_values        (data/lab_ranges.json)
                     │                     └ submit_report (structured JSON)
                     │                └─ deterministic re-check of warnings + lab flags (source of truth)
                     ├─ /api/profiles/{id}/plan      1-0-1 / BD / TDS / HS → dated doses
                     ├─ /api/profiles/{id}/alarms    polled by the app → full-screen alarm
                     └─ APScheduler tick (20 s): pending → alarming → call → caregiver SMS → missed
                                            all course doses taken → completion SMS
```

## REST API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/verify-phone` | create account and verify the registered mobile |
| POST | `/api/auth/login`, `/api/auth/logout` | start/end a sign-in session |
| POST | `/api/auth/forgot-password`, `/api/auth/reset-password` | request and use an SMS password-reset code |
| POST | `/api/chat` | ask a medication-information question (signed-in session required) |
| POST | `/api/analyze` | multipart `file`, `language`, `sex`, `force` → structured report |
| GET/PUT | `/api/profiles/{id}` | caregiver, language, dose times, escalation windows |
| POST | `/api/profiles/{id}/plan` | create dated doses from medicines |
| GET | `/api/profiles/{id}/schedule` | today's doses grouped by slot |
| GET | `/api/profiles/{id}/alarms` | doses ringing now |
| POST | `/api/doses/{id}/confirm` | "I took it" |
| POST | `/api/doses/{id}/fire` | demo: make a dose due now |
| POST | `/api/webhooks/twilio/status` | call status callback |

## Safety guardrails
- **Blurry / dark / low-res photo** → rejected with advice to retake, or ask a pharmacist (user may override with "Try anyway", which then forces a verification step).
- **Low confidence** (overall < 0.65 or any medicine < 0.6) → red/amber banner, items marked *Unclear*, and reminders can't be created until the user ticks "I will confirm with my pharmacist/doctor".
- The model is told never to guess unreadable text. Interaction/duplicate/lab checks are re-run in plain code, not trusted from the model.
- Always shows a "not a substitute for your doctor" disclaimer.

## Tests
`cd backend && pytest` (auth/recovery, medication chat, course reminders, schedule parsing, lab flags, interactions, duplicates).

## Known limits / next steps
- Reference interaction & brand tables are small starter sets — replace with RxNorm / a licensed DB for production.
- Marathi: Twilio has no Marathi TTS voice; the call uses a Hindi voice reading Devanagari. Use "missed call" mode (`CALL_MODE=missed`) or another TTS provider if quality matters.
- Browsers can't ring an alarm when the tab is closed/phone locked; that is exactly what the voice-call fallback covers. Add Web Push / a PWA wrapper for background alerts.
- This starter app does not yet include production-grade security controls such as account lockout, phone-number change verification, health-data encryption, consent, or retention policies.
- Twilio trial accounts can only call verified numbers. WhatsApp needs an approved sender.

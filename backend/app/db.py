import contextlib
import sqlite3

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY,
  name TEXT DEFAULT '',
  phone TEXT DEFAULT '',
  caregiver_phone TEXT DEFAULT '',
  language TEXT DEFAULT 'en',
  tz TEXT DEFAULT 'Asia/Kolkata',
  t_morning TEXT DEFAULT '08:00',
  t_afternoon TEXT DEFAULT '14:00',
  t_evening TEXT DEFAULT '18:00',
  t_night TEXT DEFAULT '21:00',
  escalation_min INTEGER DEFAULT 10,
  caregiver_min INTEGER DEFAULT 10,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL UNIQUE,
  profile_id TEXT NOT NULL UNIQUE,
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  is_verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(profile_id) REFERENCES profiles(id)
);
CREATE TABLE IF NOT EXISTS auth_challenges (
  phone TEXT NOT NULL,
  purpose TEXT NOT NULL,
  code_salt TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  PRIMARY KEY(phone, purpose)
);
CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS medication_courses (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  med_name TEXT NOT NULL,
  strength TEXT DEFAULT '',
  planned_doses INTEGER NOT NULL,
  completion_notified_at TEXT,
  completion_status TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(profile_id) REFERENCES profiles(id)
);
CREATE TABLE IF NOT EXISTS doses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id TEXT NOT NULL,
  course_id TEXT,
  med_name TEXT NOT NULL,
  strength TEXT DEFAULT '',
  quantity REAL DEFAULT 1,
  slot TEXT NOT NULL,
  food_timing TEXT DEFAULT 'any',
  instructions TEXT DEFAULT '',
  scheduled_at TEXT NOT NULL,          -- UTC ISO
  status TEXT DEFAULT 'pending',       -- pending | alarming | taken | missed
  alarm_at TEXT,
  call_at TEXT,
  call_sid TEXT,
  call_status TEXT,
  caregiver_at TEXT,
  taken_at TEXT,
  FOREIGN KEY(profile_id) REFERENCES profiles(id)
);
CREATE INDEX IF NOT EXISTS idx_doses_status ON doses(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_doses_profile ON doses(profile_id, scheduled_at);
"""


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(settings.db_path, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


@contextlib.contextmanager
def get_db():
    c = _connect()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)
        dose_columns = {row["name"] for row in db.execute("PRAGMA table_info(doses)")}
        if "course_id" not in dose_columns:
            db.execute("ALTER TABLE doses ADD COLUMN course_id TEXT")

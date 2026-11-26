import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_db
from .schemas import LoginIn, PhoneIn, PhoneCodeIn, ResetPasswordIn, ResendCodeIn, SignUpIn
from .services import notifier
from .services.schedule import iso, parse_iso

log = logging.getLogger("medlens.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
PASSWORD_ITERATIONS = 260_000
CODE_LIFETIME = timedelta(minutes=10)
CODE_COOLDOWN = timedelta(seconds=60)
SESSION_LIFETIME = timedelta(days=30)
MAX_CODE_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return salt.hex(), digest.hex()


def _password_matches(password: str, salt_hex: str, digest_hex: str) -> bool:
    _, digest = _hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, digest_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_code(db, phone: str, purpose: str) -> str:
    now = _now()
    existing = db.execute(
        "SELECT created_at FROM auth_challenges WHERE phone=? AND purpose=?", (phone, purpose)
    ).fetchone()
    if existing and now - parse_iso(existing["created_at"]) < CODE_COOLDOWN:
        raise HTTPException(429, "Please wait a minute before requesting another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_bytes(16)
    digest = hashlib.sha256(salt + code.encode()).hexdigest()
    db.execute(
        "INSERT OR REPLACE INTO auth_challenges "
        "(phone, purpose, code_salt, code_hash, expires_at, attempts, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (phone, purpose, salt.hex(), digest, iso(now + CODE_LIFETIME), iso(now)),
    )
    return code


def _send_code(phone: str, code: str, purpose: str) -> None:
    try:
        notifier.send_auth_code(phone, code, purpose)
    except Exception as exc:
        log.exception("Could not send %s verification SMS", purpose)
        raise HTTPException(502, "Could not send the SMS code. Please try again later.") from exc


def _consume_code(db, phone: str, purpose: str, code: str) -> str:
    challenge = db.execute(
        "SELECT * FROM auth_challenges WHERE phone=? AND purpose=?", (phone, purpose)
    ).fetchone()
    if not challenge:
        return "invalid"
    if parse_iso(challenge["expires_at"]) <= _now():
        db.execute("DELETE FROM auth_challenges WHERE phone=? AND purpose=?", (phone, purpose))
        return "expired"
    if challenge["attempts"] >= MAX_CODE_ATTEMPTS:
        return "locked"

    digest = hashlib.sha256(bytes.fromhex(challenge["code_salt"]) + code.encode()).hexdigest()
    if not hmac.compare_digest(digest, challenge["code_hash"]):
        db.execute(
            "UPDATE auth_challenges SET attempts=attempts+1 WHERE phone=? AND purpose=?",
            (phone, purpose),
        )
        return "invalid"
    db.execute("DELETE FROM auth_challenges WHERE phone=? AND purpose=?", (phone, purpose))
    return "ok"


def _new_session(db, account_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (iso(now),))
    db.execute(
        "INSERT INTO auth_sessions (token_hash, account_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (_token_hash(token), account_id, iso(now + SESSION_LIFETIME), iso(now)),
    )
    return token


def _profile(db, profile_id: str) -> dict:
    row = db.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if not row:
        raise HTTPException(401, "Account profile is unavailable.")
    return dict(row)


def _session_response(db, account) -> dict:
    token = _new_session(db, account["id"])
    return {"token": token, "profile": _profile(db, account["profile_id"])}


def current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Please sign in.", headers={"WWW-Authenticate": "Bearer"})
    with get_db() as db:
        account = db.execute(
            "SELECT a.id, a.phone, a.profile_id, s.token_hash "
            "FROM auth_sessions s JOIN accounts a ON a.id=s.account_id "
            "WHERE s.token_hash=? AND s.expires_at>?",
            (_token_hash(credentials.credentials), iso(_now())),
        ).fetchone()
    if not account:
        raise HTTPException(401, "Session expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    return dict(account)


@router.post("/signup")
def signup(body: SignUpIn):
    with get_db() as db:
        account = db.execute("SELECT * FROM accounts WHERE phone=?", (body.phone,)).fetchone()
        if account and account["is_verified"]:
            raise HTTPException(409, "An account already uses this phone number. Please sign in.")

        salt, digest = _hash_password(body.password)
        if account:
            db.execute(
                "UPDATE accounts SET password_salt=?, password_hash=? WHERE id=?",
                (salt, digest, account["id"]),
            )
        else:
            profile_id = secrets.token_hex(16)
            now = iso(_now())
            db.execute(
                "INSERT INTO profiles (id, name, phone, created_at) VALUES (?, ?, ?, ?)",
                (profile_id, body.name.strip(), body.phone, now),
            )
            db.execute(
                "INSERT INTO accounts (phone, profile_id, password_salt, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (body.phone, profile_id, salt, digest, now),
            )
        code = _issue_code(db, body.phone, "signup")
    _send_code(body.phone, code, "signup")
    return {"message": "Enter the verification code sent to your phone."}


@router.post("/verify-phone")
def verify_phone(body: PhoneCodeIn):
    response = None
    with get_db() as db:
        account = db.execute("SELECT * FROM accounts WHERE phone=?", (body.phone,)).fetchone()
        outcome = _consume_code(db, body.phone, "signup", body.code) if account else "invalid"
        if account and outcome == "ok":
            db.execute("UPDATE accounts SET is_verified=1 WHERE id=?", (account["id"],))
            account = db.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone()
            response = _session_response(db, account)
    if outcome != "ok":
        raise HTTPException(400, "Invalid or expired code. Request a new one if needed.")
    return response


@router.post("/resend-code")
def resend_code(body: ResendCodeIn):
    with get_db() as db:
        account = db.execute("SELECT is_verified FROM accounts WHERE phone=?", (body.phone,)).fetchone()
        if (
            not account
            or (body.purpose == "signup" and account["is_verified"])
            or (body.purpose == "reset" and not account["is_verified"])
        ):
            return {"message": "If the account can receive a code, one will be sent."}
        code = _issue_code(db, body.phone, body.purpose)
    _send_code(body.phone, code, body.purpose)
    return {"message": "A new code has been sent if the account can receive one."}


@router.post("/login")
def login(body: LoginIn):
    with get_db() as db:
        account = db.execute("SELECT * FROM accounts WHERE phone=?", (body.phone,)).fetchone()
        if account:
            matches = _password_matches(body.password, account["password_salt"], account["password_hash"])
        else:
            _hash_password(body.password, b"medlens-dummy-salt")
            matches = False
        if not account or not matches:
            raise HTTPException(401, "Phone number or password is incorrect.")
        if not account["is_verified"]:
            raise HTTPException(403, "Verify your phone number before signing in.")
        return _session_response(db, account)


@router.post("/forgot-password")
def forgot_password(body: PhoneIn):
    with get_db() as db:
        account = db.execute(
            "SELECT is_verified FROM accounts WHERE phone=?", (body.phone,)
        ).fetchone()
        if account and account["is_verified"]:
            code = _issue_code(db, body.phone, "reset")
        else:
            code = None
    if code:
        _send_code(body.phone, code, "reset")
    return {"message": "If a verified account exists for this phone, a reset code will be sent."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn):
    outcome = "invalid"
    with get_db() as db:
        account = db.execute(
            "SELECT * FROM accounts WHERE phone=? AND is_verified=1", (body.phone,)
        ).fetchone()
        if account:
            outcome = _consume_code(db, body.phone, "reset", body.code)
            if outcome == "ok":
                salt, digest = _hash_password(body.new_password)
                db.execute(
                    "UPDATE accounts SET password_salt=?, password_hash=? WHERE id=?",
                    (salt, digest, account["id"]),
                )
                db.execute("DELETE FROM auth_sessions WHERE account_id=?", (account["id"],))
    if outcome != "ok":
        raise HTTPException(400, "Invalid or expired code. Request a new one if needed.")
    return {"message": "Password reset. Please sign in with your new password."}


@router.get("/me")
def me(account: dict = Depends(current_account)):
    with get_db() as db:
        return _profile(db, account["profile_id"])


@router.post("/logout")
def logout(account: dict = Depends(current_account)):
    with get_db() as db:
        db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (account["token_hash"],))
    return {"ok": True}

import os
from dotenv import load_dotenv

load_dotenv()


def _bool(v: str) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


class Settings:
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.getenv("TWILIO_FROM_NUMBER", "")
    call_mode = os.getenv("CALL_MODE", "voice")
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    db_path = os.getenv("DB_PATH", "medlens.db")
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
    demo_mode = _bool(os.getenv("DEMO_MODE", "true"))
    max_upload_mb = 10

    @property
    def twilio_ready(self) -> bool:
        return bool(self.twilio_sid and self.twilio_token and self.twilio_from)


settings = Settings()

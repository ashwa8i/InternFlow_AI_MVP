import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "InternFlow AI")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///internflow.db")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-latest")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
APP_SECRET = os.getenv("APP_SECRET", "change-this-for-local-demo")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip()
GOOGLE_MEET_DURATION_MINUTES = int(os.getenv("GOOGLE_MEET_DURATION_MINUTES", "30"))

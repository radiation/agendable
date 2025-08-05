import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# pull in your repo-root .env
load_dotenv()


class Settings(BaseSettings):
    # This prevents duplicate redis events
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "web-ui")

    USER_API_BASE: str = os.getenv("USER_API_BASE", "http://user-service:8004")
    MEETING_API_BASE: str = os.getenv("MEETING_API_BASE", "http://meeting-service:8005")

    # This file is in app.core so we need to go up twice
    APP_DIR: Path = Path(__file__).parent.parent
    TEMPLATES_DIR: Path = APP_DIR / "templates"
    STATIC_DIR: Path = APP_DIR / "static"

    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()

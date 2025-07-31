import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# pull in your repo-root .env
load_dotenv()


class Settings(BaseSettings):
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "web-ui")

    # point at your Kong gateway + host-based or path-based route
    USER_API_BASE: str = os.getenv(
        "USER_API_BASE", "http://user-api.agendable.local:8000"
    )
    MEETING_API_BASE: str = os.getenv(
        "MEETING_API_BASE", "http://meeting-api.agendable.local:8000"
    )

    # any other flags you need…
    # DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"


settings = Settings()

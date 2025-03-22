import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"
    DATABASE_URL: str = "sqlite:///./test.db"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_secret_key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        from_attributes = True


settings = Settings()

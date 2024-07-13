from pydantic import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "super_duper_secret_key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        env_file = ".env"


settings = Settings()
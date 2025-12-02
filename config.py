from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "SEIGE Runner API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "securerandomsecret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./dev.db"
    CORE_ENGINE_HOST: str = "http://example:9000"

    # SSH tunnel and remote PostgreSQL settings (override via environment/.env)
    USE_SSH_TUNNEL: bool = True
    SSH_HOST: Optional[str] = None
    SSH_PORT: int = 22
    SSH_USERNAME: Optional[str] = None
    SSH_PASSWORD: Optional[str] = None

    DB_HOST: str = "127.0.0.1"  # host of the DB from the SSH server's perspective
    DB_PORT: int = 5432
    DB_NAME: Optional[str] = "seige_db"
    DB_USERNAME: Optional[str] = "seige"
    DB_PASSWORD: Optional[str] = None

    CORS_ORIGINS: list = [
        "https://seige-runner-dashboa-jjos.bolt.host",
        "http://localhost:5173",
        "http://localhost:3000",
    ]


    class Config:
        env_file = ".env"


settings = Settings()
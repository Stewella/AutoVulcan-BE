from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "SEIGE Runner API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "securerandomsecret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./dev.db"
    CORE_ENGINE_HOST: str = "http://example:9000"
    CORS_ORIGINS: list = [
        "https://seige-runner-dashboa-jjos.bolt.host",
        "http://localhost:5173",
        "http://localhost:3000",
    ]


    class Config:
        env_file = ".env"


settings = Settings()
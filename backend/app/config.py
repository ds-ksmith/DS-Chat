from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    session_https_only: bool = True
    session_max_age_seconds: int = 60 * 60 * 24 * 14


settings = Settings()

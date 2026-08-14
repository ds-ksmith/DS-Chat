from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    session_secret: str
    session_https_only: bool = True
    session_max_age_seconds: int = 60 * 60 * 24 * 14

    # Optional: push notifications are skipped (logged, not an error) if
    # unset, so existing deployments don't have to configure this to keep
    # running. Generate a pair with `python -m app.cli generate-vapid-keys`.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@example.com"


settings = Settings()

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Norrviq Måleri AB Estimator"
    default_lang: str = "ru"
    database_url: str = "sqlite:///./norrviq.db"

    app_secret_key: str = ""
    admin_email: str = ""
    admin_password: str = ""
    allow_dev_defaults: bool = False

    session_cookie_name: str = "norrviq_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 7

    log_format: str = "pretty"
    log_level: str = "INFO"

    @property
    def admin_username(self) -> str:
        return self.admin_email

    @property
    def secret_key(self) -> str:
        return self.app_secret_key

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

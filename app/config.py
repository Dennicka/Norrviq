from functools import lru_cache
from secrets import token_urlsafe

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Estimator"
    default_lang: str = "ru"
    database_url: str = "sqlite:///./norrviq.db"

    app_env: str = "local"
    session_secret: str = ""
    admin_bootstrap_enabled: bool = False
    admin_email: str = ""
    admin_password: str = ""
    allow_dev_defaults: bool = False

    session_cookie_name: str = "norrviq_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 7
    cookie_secure: bool = False
    cookie_same_site: str = "lax"

    log_format: str = "pretty"
    log_level: str = "INFO"

    backup_dir: str = "./backups"
    backup_retention_days: int = 30
    backup_max_files: int = 50

    def model_post_init(self, __context) -> None:
        if not self.session_secret and self.app_env == "local":
            self.session_secret = token_urlsafe(32)

    @property
    def admin_username(self) -> str:
        return self.admin_email

    @property
    def secret_key(self) -> str:
        return self.session_secret

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

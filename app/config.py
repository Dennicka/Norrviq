from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Norrviq Måleri AB Estimator"
    default_lang: str = "ru"
    database_url: str = "sqlite:///./norrviq.db"
    admin_username: str = "admin"
    admin_password: str = "admin"
    secret_key: str = "change-me"
    session_cookie_name: str = "norrviq_session"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

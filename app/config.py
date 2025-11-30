from functools import lru_cache
from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Norrviq Måleri AB Estimator"
    default_lang: str = "ru"
    database_url: str = "sqlite:///./norrviq.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()

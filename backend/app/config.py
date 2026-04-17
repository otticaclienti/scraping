from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://scraper:scraper@postgres:5432/scraper"
    redis_url: str = "redis://redis:6379/0"
    worker_concurrency: int = 50

    default_timeout_seconds: int = 15
    default_max_pages_per_site: int = 8
    default_max_attempts: int = 2
    default_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )


settings = Settings()

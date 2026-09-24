from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://eproc:eproc@localhost:5432/eproc_tracker"
    scraper_timeout_seconds: int = 25
    scraper_max_concurrency: int = 1
    scraper_use_xvfb: bool = True
    chrome_binary: str | None = None
    log_level: str = "INFO"


settings = Settings()

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    github_token: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""

    pdf_storage_dir: Path = Path("./data/pdfs")
    database_url: str = "sqlite:///./data/catalog.db"
    scheduler_hour: int = 8
    scheduler_minute: int = 0
    rate_limit_delay: int = 30
    full_scan_max_pages: int = 20
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    @property
    def has_github(self) -> bool:
        return bool(self.github_token)

settings = Settings()
settings.pdf_storage_dir.mkdir(parents=True, exist_ok=True)

"""
config.py — Configurações centralizadas via Pydantic Settings

Lê variáveis do .env automaticamente.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM APIs
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # Storage
    pdf_storage_dir: Path = Path("./data/pdfs")
    database_url: str = "sqlite:///./data/catalog.db"

    # Scheduler
    scheduler_hour: int = 8
    scheduler_minute: int = 0

    # Rate limiting
    rate_limit_delay: int = 30  # segundos entre requests ao mesmo domínio

    # PDF Processing
    full_scan_max_pages: int = 20

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()

# Garante que o diretório de PDFs existe
settings.pdf_storage_dir.mkdir(parents=True, exist_ok=True)

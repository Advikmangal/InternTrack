from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://interntrack:change-me@localhost:5432/interntrack'
    upload_dir: Path = Path('uploads')
    max_upload_mb: int = 5
    cookie_secure: bool = False
    cookie_name: str = 'interntrack_session'
    session_days: int = 7
    allowed_origins: list[str] = ['http://127.0.0.1:8000', 'http://localhost:8000']


settings = Settings()

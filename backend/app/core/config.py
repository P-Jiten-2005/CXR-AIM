import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Shooting Target Analysis Platform"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'target_analysis.db'))}"
    UPLOAD_DIR: str = "uploads"
    CORS_ORIGINS: List[str] = ["*"]
    SAHI_ENABLED: bool = False
    SAHI_MIN_ROI_SIZE: float = 32.0

    class Config:
        case_sensitive = True

settings = Settings()

# Ensure uploads directory and data directory exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

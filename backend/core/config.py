from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    # Application
    app_name: str = "AutoForm Backend"
    debug: bool = False
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    webhook_base_url: Optional[str] = None

    # CORS Origins - comma-separated list
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        origins = self.cors_origins.split(",")
        return [origin.strip() for origin in origins if origin.strip()]

    # Database
    database_url: str

    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    encryption_key: Optional[str] = None

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str

    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"


    # Email (optional - if not configured, emails will be logged)
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: str = "noreply@autoform.dev"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

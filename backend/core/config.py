from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "AutoForm Backend"
    debug: bool = False
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    
    # Database
    database_url: str
    
    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    
    # AWS
    aws_region: str = "us-east-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
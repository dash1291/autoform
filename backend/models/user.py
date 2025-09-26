from sqlmodel import Field, SQLModel
from typing import Optional
from datetime import datetime
from .base import BaseModel


class User(BaseModel, table=True):
    __tablename__ = "users"
    
    name: Optional[str] = None
    email: Optional[str] = Field(default=None, unique=True, index=True)
    email_verified: Optional[datetime] = None
    image: Optional[str] = None
    github_id: Optional[str] = Field(default=None, unique=True, index=True)
    
    # Relationships will be added after other models are defined


class Account(BaseModel, table=True):
    __tablename__ = "accounts"
    
    user_id: str = Field(foreign_key="users.id")
    type: str
    provider: str
    provider_account_id: str
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    expires_at: Optional[int] = None
    token_type: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None
    session_state: Optional[str] = None
    refresh_token_expires_in: Optional[int] = None


class Session(BaseModel, table=True):
    __tablename__ = "sessions"
    
    session_token: str = Field(unique=True, index=True)
    user_id: str = Field(foreign_key="users.id")
    expires: datetime


class VerificationToken(SQLModel, table=True):
    __tablename__ = "verification_tokens"
    
    identifier: str = Field(primary_key=True)
    token: str = Field(unique=True)
    expires: datetime


class UserAWSConfig(BaseModel, table=True):
    __tablename__ = "user_aws_configs"
    
    user_id: str = Field(foreign_key="users.id", unique=True)
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = Field(default="us-east-1")
    is_active: bool = Field(default=True)
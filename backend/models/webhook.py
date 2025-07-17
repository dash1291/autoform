from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime
from .base import BaseModel


class Webhook(BaseModel, table=True):
    __tablename__ = "webhooks"
    
    git_repo_url: str = Field(unique=True)
    secret: str
    is_active: bool = Field(default=True)
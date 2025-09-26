from sqlmodel import Field
from .base import BaseModel


class Webhook(BaseModel, table=True):
    __tablename__ = "webhooks"
    
    git_repo_url: str = Field(unique=True)
    secret: str
    is_active: bool = Field(default=True)
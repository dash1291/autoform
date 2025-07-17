from datetime import datetime
from typing import Optional
import uuid
from sqlmodel import Field, SQLModel


def generate_cuid() -> str:
    """Generate a CUID-like string for ID fields"""
    # For simplicity, using UUID4. In production, you might want to use a proper CUID library
    return str(uuid.uuid4())


class BaseModel(SQLModel):
    """Base model with common fields"""
    id: str = Field(default_factory=generate_cuid, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
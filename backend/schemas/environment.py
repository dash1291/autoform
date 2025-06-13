from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class EnvironmentVariableBase(BaseModel):
    key: str
    value: Optional[str] = None
    is_secret: bool = Field(False, alias="isSecret")

    class Config:
        populate_by_name = True


class EnvironmentVariableCreate(EnvironmentVariableBase):
    secret_key: Optional[str] = Field(None, alias="secretKey")

    class Config:
        populate_by_name = True


class EnvironmentVariableUpdate(BaseModel):
    value: Optional[str] = None
    is_secret: Optional[bool] = Field(None, alias="isSecret")
    secret_key: Optional[str] = Field(None, alias="secretKey")

    class Config:
        populate_by_name = True


class EnvironmentVariable(EnvironmentVariableBase):
    id: str
    project_id: str = Field(alias="projectId")
    secret_key: Optional[str] = Field(None, alias="secretKey")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True
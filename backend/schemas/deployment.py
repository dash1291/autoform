from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DeploymentStatus(str, Enum):
    PENDING = "PENDING"
    BUILDING = "BUILDING"
    PUSHING = "PUSHING"
    PROVISIONING = "PROVISIONING"
    DEPLOYING = "DEPLOYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class DeploymentBase(BaseModel):
    project_id: str = Field(alias="projectId")
    environment_id: Optional[str] = Field(None, alias="environmentId")
    image_tag: str = Field(alias="imageTag")
    commit_sha: str = Field(alias="commitSha")

    class Config:
        populate_by_name = True


class DeploymentCreate(DeploymentBase):
    pass


class Deployment(DeploymentBase):
    id: str
    status: DeploymentStatus
    logs: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True

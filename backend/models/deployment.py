from sqlmodel import Field, SQLModel
from typing import Optional
from enum import Enum
from .base import BaseModel


class DeploymentStatus(str, Enum):
    PENDING = "PENDING"
    BUILDING = "BUILDING"
    PUSHING = "PUSHING"
    PROVISIONING = "PROVISIONING"
    DEPLOYING = "DEPLOYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Deployment(BaseModel, table=True):
    __tablename__ = "deployments"
    
    project_id: str = Field(foreign_key="projects.id")
    environment_id: Optional[str] = Field(default=None, foreign_key="environments.id")
    status: DeploymentStatus = Field(default=DeploymentStatus.PENDING)
    image_tag: str
    commit_sha: str
    logs: Optional[str] = None
    details: Optional[str] = None
    celery_task_id: Optional[str] = None


class DeploymentCreate(SQLModel):
    project_id: str
    environment_id: Optional[str] = None
    image_tag: str
    commit_sha: str


class DeploymentUpdate(SQLModel):
    status: Optional[DeploymentStatus] = None
    logs: Optional[str] = None
    details: Optional[str] = None
    celery_task_id: Optional[str] = None
from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .base import BaseModel


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    CLONING = "CLONING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"


class Project(BaseModel, table=True):
    __tablename__ = "projects"
    
    name: str
    git_repo_url: str
    branch: str = Field(default="main")
    user_id: str = Field(foreign_key="users.id")
    team_id: Optional[str] = Field(default=None, foreign_key="teams.id")
    status: ProjectStatus = Field(default=ProjectStatus.CREATED)
    ecs_cluster_arn: Optional[str] = None
    ecs_service_arn: Optional[str] = None
    alb_arn: Optional[str] = None
    domain: Optional[str] = None
    existing_vpc_id: Optional[str] = None
    existing_subnet_ids: Optional[str] = None
    existing_cluster_arn: Optional[str] = None
    cpu: int = Field(default=256)
    memory: int = Field(default=512)
    disk_size: int = Field(default=21)
    subdirectory: Optional[str] = None
    port: int = Field(default=3000)
    health_check_path: str = Field(default="/")
    auto_deploy_enabled: bool = Field(default=False)
    webhook_id: Optional[str] = Field(default=None, foreign_key="webhooks.id")
    webhook_configured: bool = Field(default=False)
    is_web_service: bool = Field(default=True)
    container_command: Optional[str] = None
    secrets_arn: Optional[str] = None
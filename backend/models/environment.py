from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .base import BaseModel


class EnvironmentStatus(str, Enum):
    CREATED = "CREATED"
    PROVISIONING = "PROVISIONING"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"
    DELETING = "DELETING"


class Environment(BaseModel, table=True):
    __tablename__ = "environments"
    
    name: str
    project_id: str = Field(foreign_key="projects.id")
    team_aws_config_id: str = Field(foreign_key="team_aws_configs.id")
    status: EnvironmentStatus = Field(default=EnvironmentStatus.CREATED)
    branch: str = Field(default="main")
    cpu: int = Field(default=256)
    memory: int = Field(default=512)
    disk_size: int = Field(default=21)
    existing_vpc_id: Optional[str] = None
    existing_subnet_ids: Optional[str] = None
    existing_cluster_arn: Optional[str] = None
    ecs_cluster_arn: Optional[str] = None
    ecs_service_arn: Optional[str] = None
    alb_arn: Optional[str] = None
    alb_name: Optional[str] = None
    domain: Optional[str] = None
    task_definition_arn: Optional[str] = None
    secrets_arn: Optional[str] = None


class EnvironmentVariable(BaseModel, table=True):
    __tablename__ = "environment_variables"
    
    environment_id: str = Field(foreign_key="environments.id")
    project_id: str = Field(foreign_key="projects.id")
    key: str
    value: Optional[str] = None
    is_secret: bool = Field(default=False)
    secret_key: Optional[str] = None
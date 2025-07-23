from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .base import BaseModel
from infrastructure.constants import (
    DEFAULT_LAUNCH_TYPE,
    DEFAULT_EC2_INSTANCE_TYPE,
    DEFAULT_EC2_MIN_SIZE,
    DEFAULT_EC2_MAX_SIZE,
    DEFAULT_EC2_DESIRED_CAPACITY,
    DEFAULT_EC2_USE_SPOT,
    DEFAULT_CAPACITY_PROVIDER_TARGET_CAPACITY,
    DEFAULT_CPU,
    DEFAULT_MEMORY,
    DEFAULT_DISK_SIZE,
)


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
    cpu: int = Field(default=DEFAULT_CPU)
    memory: int = Field(default=DEFAULT_MEMORY)
    disk_size: int = Field(default=DEFAULT_DISK_SIZE)
    launch_type: str = Field(default=DEFAULT_LAUNCH_TYPE)
    ec2_instance_type: str = Field(default=DEFAULT_EC2_INSTANCE_TYPE)
    ec2_min_size: int = Field(default=DEFAULT_EC2_MIN_SIZE)
    ec2_max_size: int = Field(default=DEFAULT_EC2_MAX_SIZE)
    ec2_desired_capacity: int = Field(default=DEFAULT_EC2_DESIRED_CAPACITY)
    ec2_use_spot: bool = Field(default=DEFAULT_EC2_USE_SPOT)
    ec2_spot_max_price: Optional[str] = None
    ec2_key_name: Optional[str] = None
    capacity_provider_target_capacity: int = Field(default=DEFAULT_CAPACITY_PROVIDER_TARGET_CAPACITY)
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
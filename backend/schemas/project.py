from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from enum import Enum


class ProjectStatus(str, Enum):
    CREATED = "CREATED"
    CLONING = "CLONING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"


class ProjectBase(BaseModel):
    name: str
    git_repo_url: str = Field(alias="gitRepoUrl")
    branch: str = "main"
    cpu: int = 256
    memory: int = 512
    disk_size: int = Field(21, alias="diskSize")
    subdirectory: Optional[str] = None
    port: int = 3000
    health_check_path: str = Field("/health", alias="healthCheckPath")
    auto_deploy_enabled: bool = Field(False, alias="autoDeployEnabled")

    @validator("git_repo_url")
    def validate_github_url(cls, v):
        import re
        pattern = r"^https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?$"
        if not re.match(pattern, v):
            raise ValueError("Please provide a valid GitHub repository URL")
        return v

    @validator("cpu")
    def validate_cpu(cls, v):
        if v < 256 or v > 4096:
            raise ValueError("CPU must be between 256 and 4096")
        return v

    @validator("memory")
    def validate_memory(cls, v):
        if v < 512 or v > 30720:
            raise ValueError("Memory must be between 512 and 30720 MB")
        return v

    @validator("disk_size")
    def validate_disk_size(cls, v):
        if v < 21 or v > 200:
            raise ValueError("Disk size must be between 21 and 200 GB")
        return v

    @validator("port")
    def validate_port(cls, v):
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @validator("health_check_path")
    def validate_health_check_path(cls, v):
        if not v.startswith("/"):
            raise ValueError("Health check path must start with /")
        return v

    class Config:
        populate_by_name = True


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    git_repo_url: Optional[str] = Field(None, alias="gitRepoUrl")
    branch: Optional[str] = None
    existing_vpc_id: Optional[str] = Field(None, alias="existingVpcId")
    existing_subnet_ids: Optional[list[str]] = Field(None, alias="existingSubnetIds")
    existing_cluster_arn: Optional[str] = Field(None, alias="existingClusterArn")
    cpu: Optional[int] = None
    memory: Optional[int] = None
    disk_size: Optional[int] = Field(None, alias="diskSize")
    subdirectory: Optional[str] = None
    port: Optional[int] = None
    health_check_path: Optional[str] = Field(None, alias="healthCheckPath")
    auto_deploy_enabled: Optional[bool] = Field(None, alias="autoDeployEnabled")
    webhook_configured: Optional[bool] = Field(None, alias="webhookConfigured")

    class Config:
        populate_by_name = True


class Project(ProjectBase):
    id: str
    user_id: str = Field(alias="userId")
    status: ProjectStatus
    ecs_cluster_arn: Optional[str] = Field(None, alias="ecsClusterArn")
    ecs_service_arn: Optional[str] = Field(None, alias="ecsServiceArn")
    alb_arn: Optional[str] = Field(None, alias="albArn")
    domain: Optional[str] = None
    existing_vpc_id: Optional[str] = Field(None, alias="existingVpcId")
    existing_subnet_ids: Optional[str] = Field(None, alias="existingSubnetIds")
    existing_cluster_arn: Optional[str] = Field(None, alias="existingClusterArn")
    secrets_arn: Optional[str] = Field(None, alias="secretsArn")
    webhook_secret: Optional[str] = Field(None, alias="webhookSecret")
    webhook_configured: bool = Field(False, alias="webhookConfigured")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True
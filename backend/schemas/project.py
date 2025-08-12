import re
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime


class ProjectBase(BaseModel):
    name: str
    git_repo_url: str = Field(alias="gitRepoUrl")
    team_id: str = Field(alias="teamId")
    auto_deploy_enabled: bool = Field(False, alias="autoDeployEnabled")

    @validator("git_repo_url")
    def validate_github_url(cls, v):
        pattern = r"^https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?$"
        if not re.match(pattern, v):
            raise ValueError("Please provide a valid GitHub repository URL")
        return v

    class Config:
        populate_by_name = True


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    git_repo_url: Optional[str] = Field(None, alias="gitRepoUrl")
    auto_deploy_enabled: Optional[bool] = Field(None, alias="autoDeployEnabled")
    subdirectory: Optional[str] = None
    port: Optional[int] = None
    health_check_path: Optional[str] = Field(None, alias="healthCheckPath")

    class Config:
        populate_by_name = True


class Project(ProjectBase):
    id: str
    webhook_id: Optional[str] = Field(None, alias="webhookId")
    subdirectory: Optional[str] = None
    port: int = 3000
    health_check_path: str = Field("/", alias="healthCheckPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    team: Optional[dict] = None  # Will include team info
    webhook_configured: Optional[bool] = Field(None, alias="webhookConfigured")  # Computed field

    class Config:
        from_attributes = True
        populate_by_name = True


# Legacy enum for backward compatibility with existing code
class ProjectStatus:
    CREATED = "CREATED"
    CLONING = "CLONING"
    BUILDING = "BUILDING"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"
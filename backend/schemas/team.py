from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TeamMemberRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class TeamMemberAdd(BaseModel):
    github_username: str = Field(alias="githubUsername")
    role: TeamMemberRole = TeamMemberRole.MEMBER

    @validator("github_username")
    def validate_github_username(cls, v):
        if len(v.strip()) < 1:
            raise ValueError("GitHub username is required")
        # Basic GitHub username validation
        import re
        if not re.match(r'^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$', v.strip()):
            raise ValueError("Invalid GitHub username format")
        return v.strip()

    class Config:
        populate_by_name = True


class TeamBase(BaseModel):
    name: str
    description: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError("Team name must be at least 2 characters long")
        return v.strip()

    class Config:
        populate_by_name = True


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None and len(v.strip()) < 2:
            raise ValueError("Team name must be at least 2 characters long")
        return v.strip() if v else v

    class Config:
        populate_by_name = True


class TeamMemberBase(BaseModel):
    user_id: str = Field(alias="userId")
    role: TeamMemberRole = TeamMemberRole.MEMBER

    class Config:
        populate_by_name = True


class TeamMember(TeamMemberBase):
    id: str
    team_id: str = Field(alias="teamId")
    joined_at: datetime = Field(alias="joinedAt")
    user: Optional[dict] = None  # Will include user info

    class Config:
        from_attributes = True
        populate_by_name = True


class Team(TeamBase):
    id: str
    owner_id: str = Field(alias="ownerId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    members: Optional[List[TeamMember]] = None
    member_count: Optional[int] = Field(None, alias="memberCount")
    user_role: Optional[TeamMemberRole] = Field(None, alias="userRole")

    class Config:
        from_attributes = True
        populate_by_name = True



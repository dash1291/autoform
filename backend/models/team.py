from sqlmodel import Field
from typing import Optional
from datetime import datetime
from enum import Enum
from .base import BaseModel


class TeamMemberRole(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class Team(BaseModel, table=True):
    __tablename__ = "teams"
    
    name: str
    description: Optional[str] = None
    owner_id: str = Field(foreign_key="users.id")


class TeamMember(BaseModel, table=True):
    __tablename__ = "team_members"
    
    team_id: str = Field(foreign_key="teams.id")
    user_id: str = Field(foreign_key="users.id")
    role: TeamMemberRole = Field(default=TeamMemberRole.MEMBER)
    joined_at: datetime = Field(default_factory=datetime.utcnow)


class TeamAwsConfig(BaseModel, table=True):
    __tablename__ = "team_aws_configs"
    
    team_id: str = Field(foreign_key="teams.id")
    name: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = Field(default="us-east-1")
    is_active: bool = Field(default=True)
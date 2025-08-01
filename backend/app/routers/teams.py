from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List, Optional
import secrets
import logging
from datetime import datetime, timedelta

from core.database import get_async_session
from core.security import get_current_user
from core.config import settings
from sqlmodel import select, and_, or_, func
from models.user import User
from models.team import Team as TeamModel, TeamMember as TeamMemberModel, TeamAwsConfig
from models.project import Project as ProjectModel
from models.environment import Environment as EnvironmentModel
from models.user import User as UserModel
from schemas import User as UserSchema
from schemas.team import (
    Team,
    TeamCreate,
    TeamUpdate,
    TeamMember,
    TeamMemberRole,
    TeamMemberAdd,
)
from services.github_user_service import github_user_service
from services.encryption_service import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Team])
async def get_user_teams(current_user: UserSchema = Depends(get_current_user)):
    """Get all teams that the current user owns or is a member of"""
    async with get_async_session() as session:
        # Get teams where user is owner
        owned_teams = await session.execute(
            select(TeamModel).where(TeamModel.owner_id == current_user.id)
        )
        
        # Get teams where user is a member
        member_team_ids = await session.execute(
            select(TeamMemberModel.team_id).where(TeamMemberModel.user_id == current_user.id)
        )
        member_teams = await session.execute(
            select(TeamModel).where(TeamModel.id.in_(member_team_ids.scalars().all()))
        )

        # Combine and deduplicate teams
        all_teams = {}
        
        # Process owned teams
        for team in owned_teams.scalars().all():
            # Get owner info (current user in this case)
            owner_result = await session.execute(
                select(UserModel).where(UserModel.id == team.owner_id)
            )
            owner = owner_result.scalar_one_or_none()
            
            members = []
            
            # Add owner as first member
            if owner:
                members.append({
                    "id": None,
                    "teamId": team.id,
                    "userId": owner.id,
                    "role": TeamMemberRole.OWNER,
                    "joinedAt": team.created_at,
                    "user": {
                        "id": owner.id,
                        "name": owner.name,
                        "email": owner.email,
                        "image": owner.image,
                        "githubId": owner.github_id,
                    }
                })
            
            # Get team members with user info
            members_result = await session.execute(
                select(TeamMemberModel, UserModel).where(
                    TeamMemberModel.team_id == team.id
                ).join(UserModel, TeamMemberModel.user_id == UserModel.id)
            )
            
            for member, user in members_result.all():
                members.append({
                    "id": member.id,
                    "teamId": member.team_id,
                    "userId": member.user_id,
                    "role": member.role,
                    "joinedAt": member.joined_at,
                    "user": {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "image": user.image,
                        "githubId": user.github_id,
                    }
                })
            
            all_teams[team.id] = {
                "id": team.id,
                "name": team.name,
                "description": team.description,
                "createdAt": team.created_at,
                "updatedAt": team.updated_at,
                "ownerId": team.owner_id,
                "members": members,
                "memberCount": len(members),
                "userRole": TeamMemberRole.OWNER,
            }
        
        # Process member teams
        for team in member_teams.scalars().all():
            if team.id not in all_teams:
                # Get owner info first
                owner_result = await session.execute(
                    select(UserModel).where(UserModel.id == team.owner_id)
                )
                owner = owner_result.scalar_one_or_none()
                
                members = []
                
                # Add owner as first member
                if owner:
                    members.append({
                        "id": None,
                        "teamId": team.id,
                        "userId": owner.id,
                        "role": TeamMemberRole.OWNER,
                        "joinedAt": team.created_at,
                        "user": {
                            "id": owner.id,
                            "name": owner.name,
                            "email": owner.email,
                            "image": owner.image,
                            "githubId": owner.github_id,
                        }
                    })
                
                # Get team members with user info
                members_result = await session.execute(
                    select(TeamMemberModel, UserModel).where(
                        TeamMemberModel.team_id == team.id
                    ).join(UserModel, TeamMemberModel.user_id == UserModel.id)
                )
                
                user_role = TeamMemberRole.MEMBER
                for member, user in members_result.all():
                    member_dict = {
                        "id": member.id,
                        "teamId": member.team_id,
                        "userId": member.user_id,
                        "role": member.role,
                        "joinedAt": member.joined_at,
                        "user": {
                            "id": user.id,
                            "name": user.name,
                            "email": user.email,
                            "image": user.image,
                            "githubId": user.github_id,
                        }
                    }
                    members.append(member_dict)
                    
                    # Update user's role if they're in the members list
                    if member.user_id == current_user.id:
                        user_role = member.role
                
                all_teams[team.id] = {
                    "id": team.id,
                    "name": team.name,
                    "description": team.description,
                    "createdAt": team.created_at,
                    "updatedAt": team.updated_at,
                    "ownerId": team.owner_id,
                    "members": members,
                    "memberCount": len(members),
                    "userRole": user_role,
                }
        
        return list(all_teams.values())


@router.post("/", response_model=Team, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate, current_user: UserSchema = Depends(get_current_user)
):
    """Create a new team"""
    
    logger.info(f"Creating team: {team_data.name} for user {current_user.id}")
    logger.info(f"Team data: {team_data}")

    async with get_async_session() as session:
        # Check if user already has a team with this name
        existing_team = await session.execute(
            select(TeamModel).where(
                and_(TeamModel.owner_id == current_user.id, TeamModel.name == team_data.name)
            )
        )

        if existing_team.scalar_one_or_none():
            logger.warning(f"Team with name {team_data.name} already exists for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a team with this name",
            )

        # Create the team
        team = TeamModel(
            name=team_data.name,
            description=team_data.description,
            owner_id=current_user.id,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(team)
        await session.commit()
        await session.refresh(team)

        logger.info(f"User {current_user.id} created team {team.id}: {team.name}")

        return {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "createdAt": team.created_at,
            "updatedAt": team.updated_at,
            "ownerId": team.owner_id,
            "memberCount": 0,
            "userRole": TeamMemberRole.OWNER
        }


@router.get("/{team_id}", response_model=Team)
async def get_team(team_id: str, current_user: User = Depends(get_current_user)):
    """Get team details"""

    async with get_async_session() as session:
        # Check if user has access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                TeamMemberModel.user_id == current_user.id
                            )
                        )
                    )
                )
            )
        )
        team = team.scalar_one_or_none()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )

        # Get owner info first
        owner_result = await session.execute(
            select(UserModel).where(UserModel.id == team.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        
        members = []
        
        # Add owner as first member
        if owner:
            members.append({
                "id": f"owner-{team.owner_id}",  # Generate a unique ID for the owner entry
                "teamId": team.id,
                "userId": owner.id,
                "role": TeamMemberRole.OWNER,
                "joinedAt": team.created_at,  # Use team creation date as owner's join date
                "user": {
                    "id": owner.id,
                    "name": owner.name,
                    "email": owner.email,
                    "image": owner.image,
                    "githubId": owner.github_id,
                }
            })
        
        # Get team members with user info
        members_result = await session.execute(
            select(TeamMemberModel, UserModel).where(
                TeamMemberModel.team_id == team_id
            ).join(UserModel, TeamMemberModel.user_id == UserModel.id)
        )
        
        for member, user in members_result.all():
            members.append({
                "id": member.id,
                "teamId": member.team_id,
                "userId": member.user_id,
                "role": member.role,
                "joinedAt": member.joined_at,
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "image": user.image,
                    "githubId": user.github_id,
                }
            })

        # Get member count
        member_count = len(members)

        # Determine user's role
        user_role = TeamMemberRole.OWNER if team.owner_id == current_user.id else TeamMemberRole.MEMBER
        
        if team.owner_id != current_user.id:
            user_member = next((m for m in members if m["userId"] == current_user.id), None)
            if user_member:
                user_role = user_member["role"]

        return {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "createdAt": team.created_at,
            "updatedAt": team.updated_at,
            "ownerId": team.owner_id,
            "members": members,
            "memberCount": member_count,
            "userRole": user_role
        }


@router.put("/{team_id}", response_model=Team)
async def update_team(
    team_id: str, team_data: TeamUpdate, current_user: User = Depends(get_current_user)
):
    """Update team details (only owner or admin can update)"""

    async with get_async_session() as session:
        # Check if user has admin access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Prepare update data
        update_data = {}
        if team_data.name is not None:
            update_data["name"] = team_data.name
        if team_data.description is not None:
            update_data["description"] = team_data.description

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
            )

        # Update team
        for key, value in update_data.items():
            setattr(team, key, value)
        team.updated_at = datetime.now()
        session.add(team)
        await session.commit()
        await session.refresh(team)

        # Get member count
        member_count_result = await session.execute(
            select(func.count(TeamMemberModel.id)).where(
                TeamMemberModel.team_id == team_id
            )
        )
        member_count = member_count_result.scalar_one()

        user_role = (
            TeamMemberRole.OWNER
            if team.owner_id == current_user.id
            else TeamMemberRole.ADMIN
        )

        logger.info(f"Team {team_id} updated by user {current_user.id}")

        return {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "createdAt": team.created_at,
            "updatedAt": team.updated_at,
            "ownerId": team.owner_id,
            "memberCount": member_count,
            "userRole": user_role
        }


@router.delete("/{team_id}")
async def delete_team(team_id: str, current_user: User = Depends(get_current_user)):
    """Delete team (only owner can delete)"""

    async with get_async_session() as session:
        # Check if user is the owner of this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    TeamModel.owner_id == current_user.id
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or you are not the owner",
            )

        # Check if team has projects
        project_count_result = await session.execute(
            select(func.count(ProjectModel.id)).where(
                ProjectModel.team_id == team_id
            )
        )
        project_count = project_count_result.scalar_one()

        if project_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete team with {project_count} projects. Move or delete projects first.",
            )

        # Delete team (this will cascade delete members and invitations)
        await session.delete(team)
        await session.commit()

        logger.info(f"Team {team_id} deleted by owner {current_user.id}")

        return {"message": "Team deleted successfully"}


@router.get("/{team_id}/members", response_model=List[TeamMember])
async def get_team_members(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get team members"""

    async with get_async_session() as session:
        # Check if user has access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                TeamMemberModel.user_id == current_user.id
                            )
                        )
                    )
                )
            )
        )
        team = team.scalar_one_or_none()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )

        # Get team members with user info
        members_result = await session.execute(
            select(TeamMemberModel, UserModel).where(
                TeamMemberModel.team_id == team_id
            ).join(UserModel, TeamMemberModel.user_id == UserModel.id)
        )
        
        members = []
        for member, user in members_result.all():
            members.append({
                "id": member.id,
                "teamId": member.team_id,
                "userId": member.user_id,
                "role": member.role,
                "joinedAt": member.joined_at,
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "image": user.image,
                    "githubId": user.github_id,
                }
            })

        return members


@router.post("/{team_id}/members")
async def add_team_member(
    team_id: str,
    member_data: TeamMemberAdd,
    current_user: User = Depends(get_current_user),
):
    """Add a user to the team by GitHub username"""

    async with get_async_session() as session:
        # Check if user has admin access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get the current user's GitHub access token
        access_token = await github_user_service.get_user_github_access_token(
            current_user.id
        )
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="GitHub access token not found. Please re-authenticate with GitHub.",
            )

        # Find or create user by GitHub username
        user_id = await github_user_service.find_or_create_user_by_github_username(
            member_data.github_username, access_token
        )

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GitHub user '{member_data.github_username}' not found",
            )

        # Check if user is already a member
        existing_member = await session.execute(
            select(TeamMemberModel).where(
                and_(
                    TeamMemberModel.team_id == team_id,
                    TeamMemberModel.user_id == user_id
                )
            )
        )
        existing_member = existing_member.scalar_one_or_none()

        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this team",
            )

        # Add user to team
        team_member = TeamMemberModel(
            team_id=team_id,
            user_id=user_id,
            role=member_data.role,
            joined_at=datetime.now()
        )
        session.add(team_member)
        await session.commit()
        await session.refresh(team_member)

        # Get user info
        user_result = await session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = user_result.scalar_one_or_none()

        logger.info(
            f"User {member_data.github_username} (ID: {user_id}) added to team {team_id} by {current_user.id}"
        )

        return {
            "id": team_member.id,
            "teamId": team_member.team_id,
            "userId": team_member.user_id,
            "role": team_member.role,
            "joinedAt": team_member.joined_at,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "image": user.image,
                "githubId": user.github_id,
            },
        }


@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str, user_id: str, current_user: User = Depends(get_current_user)
):
    """Remove a member from the team"""

    async with get_async_session() as session:
        # Check if current user has admin access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Cannot remove the team owner
        if user_id == team.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the team owner",
            )

        # Find the member to remove
        member = await session.execute(
            select(TeamMemberModel).where(
                and_(
                    TeamMemberModel.team_id == team_id,
                    TeamMemberModel.user_id == user_id
                )
            )
        )
        member = member.scalar_one_or_none()

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a member of this team",
            )

        # Remove the member
        await session.delete(member)
        await session.commit()

        logger.info(f"User {user_id} removed from team {team_id} by {current_user.id}")

        return {"message": "Member removed successfully"}


@router.put("/{team_id}/members/{user_id}/role")
async def update_member_role(
    team_id: str,
    user_id: str,
    role_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update a team member's role"""

    new_role = role_data.get("role")
    if new_role not in [role.value for role in TeamMemberRole]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role"
        )

    async with get_async_session() as session:
        # Check if current user is the team owner
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    TeamModel.owner_id == current_user.id
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or you are not the owner",
            )

        # Cannot change owner role
        if user_id == team.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change the owner's role",
            )

        # Find the member
        member = await session.execute(
            select(TeamMemberModel).where(
                and_(
                    TeamMemberModel.team_id == team_id,
                    TeamMemberModel.user_id == user_id
                )
            )
        )
        member = member.scalar_one_or_none()

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not a member of this team",
            )

        # Update the role
        member.role = new_role
        session.add(member)
        await session.commit()

        logger.info(
            f"User {user_id} role updated to {new_role} in team {team_id} by {current_user.id}"
        )

        return {"message": f"Member role updated to {new_role}"}


@router.get("/{team_id}/aws-config")
async def get_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get team AWS configuration (only shows if configured)"""

    async with get_async_session() as session:
        # Check if user is team owner or admin
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get AWS config
        aws_config_result = await session.execute(
            select(TeamAwsConfig).where(and_(TeamAwsConfig.team_id == team_id, TeamAwsConfig.is_active == True))
        )
        result = aws_config_result.first()
        aws_config = result[0] if result else None

        if not aws_config:
            return {"configured": False, "isActive": False}

        # Decrypt and mask the access key ID for display
        masked_access_key = None
        if aws_config.aws_access_key_id:
            try:
                decrypted_access_key = encryption_service.decrypt(aws_config.aws_access_key_id)
                if decrypted_access_key and len(decrypted_access_key) >= 4:
                    # Mask the access key ID properly (AKIA... -> AKIA************)
                    masked_access_key = (
                        f"{decrypted_access_key[:4]}{'*' * (len(decrypted_access_key) - 4)}"
                    )
                else:
                    masked_access_key = "****"
            except Exception:
                masked_access_key = "****"

        # Don't expose the actual credentials, just show masked version
        return {
            "configured": True,
            "isActive": aws_config.is_active,
            "awsRegion": aws_config.aws_region,
            "awsAccessKeyId": masked_access_key,
            "awsSecretAccessKey": "****************************"
            if aws_config.aws_secret_access_key
            else None,
            "createdAt": aws_config.created_at,
            "updatedAt": aws_config.updated_at,
        }


@router.post("/{team_id}/aws-config")
async def create_or_update_team_aws_config(
    team_id: str, config_data: dict, current_user: User = Depends(get_current_user)
):
    """Create or update team AWS configuration"""

    async with get_async_session() as session:
        # Check if user is team owner
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    TeamModel.owner_id == current_user.id
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or you are not the owner",
            )

        # Validate required fields
        aws_access_key_id = config_data.get("awsAccessKeyId")
        aws_secret_access_key = config_data.get("awsSecretAccessKey")
        aws_region = config_data.get("awsRegion", "us-east-1")
        
        # Auto-generate name if not provided
        if "name" in config_data:
            name = config_data["name"]
        else:
            # Check how many configs exist to generate a meaningful name
            existing_configs = await session.execute(
                select(TeamAwsConfig).where(TeamAwsConfig.team_id == team_id)
            )
            existing_configs_list = existing_configs.scalars().all()
            if len(existing_configs_list) == 0:
                name = "Primary"
            else:
                name = f"Config {len(existing_configs_list) + 1}"

        if not aws_access_key_id or not aws_secret_access_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS Access Key ID and Secret Access Key are required",
            )

        # Encrypt credentials
        encrypted_access_key = encryption_service.encrypt(aws_access_key_id)
        encrypted_secret_key = encryption_service.encrypt(aws_secret_access_key)

        # Check if config already exists
        existing_config = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.team_id == team_id)
        )
        existing_config = existing_config.scalar_one_or_none()

        if existing_config:
            # Update existing config
            existing_config.aws_access_key_id = encrypted_access_key
            existing_config.aws_secret_access_key = encrypted_secret_key
            existing_config.aws_region = aws_region
            existing_config.is_active = True
            existing_config.updated_at = datetime.now()
            session.add(existing_config)
            await session.commit()
            logger.info(f"Team {team_id} AWS config updated by {current_user.id}")
            return {"message": "AWS configuration updated successfully"}
        else:
            # Create new config
            new_config = TeamAwsConfig(
                team_id=team_id,
                name=name,
                aws_access_key_id=encrypted_access_key,
                aws_secret_access_key=encrypted_secret_key,
                aws_region=aws_region,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(new_config)
            await session.commit()
            logger.info(f"Team {team_id} AWS config created by {current_user.id}")
            return {"message": "AWS configuration created successfully"}


@router.delete("/{team_id}/aws-config")
async def delete_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Delete team AWS configuration"""

    async with get_async_session() as session:
        # Check if user is team owner
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    TeamModel.owner_id == current_user.id
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or you are not the owner",
            )

        # Delete AWS config
        configs_to_delete = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.team_id == team_id)
        )
        configs_list = configs_to_delete.scalars().all()
        
        if configs_list:
            for config in configs_list:
                await session.delete(config)
            await session.commit()
            logger.info(f"Team {team_id} AWS config deleted by {current_user.id}")
            return {"message": "AWS configuration deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No AWS configuration found for this team",
            )


@router.post("/{team_id}/aws-config/test")
async def test_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Test team AWS configuration by attempting to list S3 buckets"""

    async with get_async_session() as session:
        # Check if user has access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get AWS config
        aws_config = await session.execute(
            select(TeamAwsConfig).where(
                and_(
                    TeamAwsConfig.team_id == team_id,
                    TeamAwsConfig.is_active == True
                )
            )
        )
        aws_config = aws_config.scalar_one_or_none()

    if not aws_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active AWS configuration found for this team",
        )

        # Decrypt credentials
        access_key = encryption_service.decrypt(aws_config.aws_access_key_id)
        secret_key = encryption_service.decrypt(aws_config.aws_secret_access_key)

    if not access_key or not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt AWS credentials",
        )

    # Test AWS credentials
    from utils.aws_client import create_client
    from botocore.exceptions import ClientError

    try:
        # Create credentials dict for AWS client
        aws_credentials = {
            "access_key": access_key,
            "secret_key": secret_key,
        }

        # Create S3 client with team credentials (LocalStack-aware)
        s3_client = create_client("s3", aws_config.aws_region, aws_credentials)

        # Try to list buckets as a test
        response = s3_client.list_buckets()
        bucket_count = len(response.get("Buckets", []))

        # Also get account info
        sts_client = create_client("sts", aws_config.aws_region, aws_credentials)

        identity = sts_client.get_caller_identity()

        return {
            "success": True,
            "message": "AWS credentials are valid",
            "accountId": identity.get("Account"),
            "userId": identity.get("UserId"),
            "arn": identity.get("Arn"),
            "bucketCount": bucket_count,
            "region": aws_config.aws_region,
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "InvalidClientTokenId":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid AWS Access Key ID. Please check your credentials.",
            )
        elif error_code == "SignatureDoesNotMatch":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid AWS Secret Access Key. Please check your credentials.",
            )
        elif error_code in ["UnauthorizedOperation", "AccessDenied", "Forbidden"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AWS credentials are valid but lack sufficient permissions. Your AWS user needs permissions for S3 and STS services.",
            )
        elif "not authorized to perform" in error_message.lower():
            # Handle specific authorization errors
            if "s3:ListBuckets" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="AWS credentials are valid but your user doesn't have permission to list S3 buckets. This is used for testing only - deployments may still work.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="AWS credentials are valid but lack some required permissions. Please ensure your AWS user has appropriate permissions.",
                )
        else:
            # Log the actual AWS error for debugging
            logger.error(
                f"AWS test error for team {team_id}: {error_code} - {error_message}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS credentials test failed: {error_message}",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing AWS credentials: {str(e)}",
        )


# New endpoints for multiple AWS configurations per team


@router.get("/{team_id}/aws-configs")
async def get_team_aws_configs(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get all AWS configurations for a team"""

    async with get_async_session() as session:
        # Check if user has access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role.in_([TeamMemberRole.ADMIN, TeamMemberRole.MEMBER])
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get all AWS configs for this team
        aws_configs = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.team_id == team_id)
        )
        aws_configs = aws_configs.scalars().all()

        configs_response = []
        for config in aws_configs:
            # Decrypt and mask the access key ID for display
            masked_access_key = "****"
            if config.aws_access_key_id:
                try:
                    decrypted_access_key = encryption_service.decrypt(config.aws_access_key_id)
                    if decrypted_access_key and len(decrypted_access_key) >= 4:
                        masked_access_key = f"{decrypted_access_key[:4]}{'*' * (len(decrypted_access_key) - 4)}"
                except Exception:
                    pass

            configs_response.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "isActive": config.is_active,
                    "awsRegion": config.aws_region,
                    "awsAccessKeyId": masked_access_key,
                    "awsSecretAccessKey": "****************************"
                    if config.aws_secret_access_key
                    else None,
                    "createdAt": config.created_at,
                    "updatedAt": config.updated_at,
                }
            )

        return configs_response


@router.post("/{team_id}/aws-configs")
async def create_team_aws_config(
    team_id: str, config_data: dict, current_user: User = Depends(get_current_user)
):
    """Create a new AWS configuration for a team"""

    async with get_async_session() as session:
        # Check if user is team owner or admin
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Validate required fields
        name = config_data.get("name", "").strip()
        aws_access_key_id = config_data.get("awsAccessKeyId", "").strip()
        aws_secret_access_key = config_data.get("awsSecretAccessKey", "").strip()
        aws_region = config_data.get("awsRegion", "us-east-1").strip()

        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration name is required",
            )

        if not aws_access_key_id or not aws_secret_access_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS Access Key ID and Secret Access Key are required",
            )

        # Check if a config with this name already exists for the team
        existing_config = await session.execute(
            select(TeamAwsConfig).where(
                and_(
                    TeamAwsConfig.team_id == team_id,
                    TeamAwsConfig.name == name
                )
            )
        )
        existing_config = existing_config.scalar_one_or_none()

        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS configuration with name '{name}' already exists for this team",
            )

        # Encrypt credentials
        encrypted_access_key = encryption_service.encrypt(aws_access_key_id)
        encrypted_secret_key = encryption_service.encrypt(aws_secret_access_key)

        # Create new config
        new_config = TeamAwsConfig(
            team_id=team_id,
            name=name,
            aws_access_key_id=encrypted_access_key,
            aws_secret_access_key=encrypted_secret_key,
            aws_region=aws_region,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_config)
        await session.commit()
        await session.refresh(new_config)

        logger.info(f"Team {team_id} AWS config '{name}' created by {current_user.id}")

        return {
            "message": f"AWS configuration '{name}' created successfully",
            "id": new_config.id,
            "name": new_config.name,
        }


@router.put("/{team_id}/aws-configs/{config_id}")
async def update_team_aws_config(
    team_id: str,
    config_id: str,
    config_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update an existing AWS configuration for a team"""

    async with get_async_session() as session:
        # Check if user is team owner or admin
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get existing config
        existing_config = await session.execute(
            select(TeamAwsConfig).where(
                and_(
                    TeamAwsConfig.id == config_id,
                    TeamAwsConfig.team_id == team_id
                )
            )
        )
        existing_config = existing_config.scalar_one_or_none()

        if not existing_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
            )

        # Validate and prepare update data
        if "name" in config_data:
            name = config_data["name"].strip()
            if not name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Configuration name cannot be empty",
                )

            # Check if another config with this name exists
            if name != existing_config.name:
                name_conflict = await session.execute(
                    select(TeamAwsConfig).where(
                        and_(
                            TeamAwsConfig.team_id == team_id,
                            TeamAwsConfig.name == name,
                            TeamAwsConfig.id != config_id
                        )
                    )
                )
                name_conflict = name_conflict.scalar_one_or_none()
                if name_conflict:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"AWS configuration with name '{name}' already exists for this team",
                    )

            existing_config.name = name

        if "awsAccessKeyId" in config_data and "awsSecretAccessKey" in config_data:
            aws_access_key_id = config_data["awsAccessKeyId"].strip()
            aws_secret_access_key = config_data["awsSecretAccessKey"].strip()

            if not aws_access_key_id or not aws_secret_access_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="AWS Access Key ID and Secret Access Key are required",
                )

            # Encrypt credentials
            existing_config.aws_access_key_id = encryption_service.encrypt(aws_access_key_id)
            existing_config.aws_secret_access_key = encryption_service.encrypt(
                aws_secret_access_key
            )

        if "awsRegion" in config_data:
            aws_region = config_data["awsRegion"].strip()
            if aws_region:
                existing_config.aws_region = aws_region

        if "isActive" in config_data:
            existing_config.is_active = bool(config_data["isActive"])

        # Update config
        existing_config.updated_at = datetime.now()
        session.add(existing_config)
        await session.commit()
        await session.refresh(existing_config)

        logger.info(
            f"Team {team_id} AWS config '{existing_config.name}' updated by {current_user.id}"
        )

        return {
            "message": f"AWS configuration '{existing_config.name}' updated successfully",
            "id": existing_config.id,
            "name": existing_config.name,
        }


@router.delete("/{team_id}/aws-configs/{config_id}")
async def delete_team_aws_config(
    team_id: str, config_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an AWS configuration for a team"""

    async with get_async_session() as session:
        # Check if user is team owner or admin
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get existing config
        existing_config = await session.execute(
            select(TeamAwsConfig).where(
                and_(
                    TeamAwsConfig.id == config_id,
                    TeamAwsConfig.team_id == team_id
                )
            )
        )
        existing_config = existing_config.scalar_one_or_none()

        if not existing_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
            )

        # Check if this config is being used by any environments
        environments_using_config = await session.execute(
            select(EnvironmentModel).where(
                EnvironmentModel.team_aws_config_id == config_id
            )
        )
        environments_using_config = environments_using_config.scalars().all()

        if environments_using_config:
            environment_names = [env.name for env in environments_using_config]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete AWS configuration '{existing_config.name}' because it is being used by environments: {', '.join(environment_names)}",
            )

        # Delete config
        await session.delete(existing_config)
        await session.commit()

        logger.info(
            f"Team {team_id} AWS config '{existing_config.name}' deleted by {current_user.id}"
        )

        return {
            "message": f"AWS configuration '{existing_config.name}' deleted successfully"
        }


@router.post("/{team_id}/aws-configs/{config_id}/test")
async def test_specific_team_aws_config(
    team_id: str, config_id: str, current_user: User = Depends(get_current_user)
):
    """Test a specific team AWS configuration"""

    async with get_async_session() as session:
        # Check if user has access to this team
        team = await session.execute(
            select(TeamModel).where(
                and_(
                    TeamModel.id == team_id,
                    or_(
                        TeamModel.owner_id == current_user.id,
                        TeamModel.id.in_(
                            select(TeamMemberModel.team_id).where(
                                and_(
                                    TeamMemberModel.user_id == current_user.id,
                                    TeamMemberModel.role == TeamMemberRole.ADMIN
                                )
                            )
                        )
                    )
                )
            )
        )
        team = team.first()

        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found or insufficient permissions",
            )

        # Get specific AWS config
        aws_config = await session.execute(
            select(TeamAwsConfig).where(
                and_(
                    TeamAwsConfig.id == config_id,
                    TeamAwsConfig.team_id == team_id
                )
            )
        )
        aws_config = aws_config.scalar_one_or_none()

        if not aws_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
            )

        # Decrypt credentials
        access_key = encryption_service.decrypt(aws_config.aws_access_key_id)
        secret_key = encryption_service.decrypt(aws_config.aws_secret_access_key)

        if not access_key or not secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt AWS credentials",
            )

    # Test AWS credentials
    from utils.aws_client import create_client
    from botocore.exceptions import ClientError

    try:
        # Create credentials dict for AWS client
        aws_credentials = {
            "access_key": access_key,
            "secret_key": secret_key,
        }

        # Create S3 client with team credentials (LocalStack-aware)
        s3_client = create_client("s3", aws_config.aws_region, aws_credentials)

        # Try to list buckets as a test
        response = s3_client.list_buckets()
        bucket_count = len(response.get("Buckets", []))

        # Also get account info
        sts_client = create_client("sts", aws_config.aws_region, aws_credentials)

        identity = sts_client.get_caller_identity()

        return {
            "success": True,
            "message": f"AWS credentials for '{aws_config.name}' are valid",
            "configName": aws_config.name,
            "accountId": identity.get("Account"),
            "userId": identity.get("UserId"),
            "arn": identity.get("Arn"),
            "bucketCount": bucket_count,
            "region": aws_config.aws_region,
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        logger.error(
            f"AWS test error for team {team_id} config {config_id}: {error_code} - {error_message}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AWS credentials test failed for '{aws_config.name}': {error_message}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing AWS credentials for '{aws_config.name}': {str(e)}",
        )

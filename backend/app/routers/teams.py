from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List, Optional
import secrets
import logging
from datetime import datetime, timedelta

from core.database import prisma
from core.security import get_current_user
from core.config import settings
from schemas import User
from schemas.team import (
    Team, TeamCreate, TeamUpdate, TeamMember, TeamMemberRole, TeamMemberAdd
)
from services.github_user_service import github_user_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Team])
async def get_user_teams(current_user: User = Depends(get_current_user)):
    """Get all teams that the current user owns or is a member of"""
    
    # Get teams where user is owner
    owned_teams = await prisma.team.find_many(
        where={"ownerId": current_user.id},
        include={
            "members": {
                "include": {
                    "user": True
                }
            }
        }
    )
    
    # Get teams where user is a member
    member_teams = await prisma.team.find_many(
        where={
            "members": {
                "some": {
                    "userId": current_user.id
                }
            }
        },
        include={
            "members": {
                "include": {
                    "user": True
                }
            }
        }
    )
    
    # Combine and deduplicate teams
    all_teams = {}
    
    for team in owned_teams:
        all_teams[team.id] = {
            **team.__dict__,
            "memberCount": len(team.members),
            "userRole": TeamMemberRole.OWNER
        }
    
    for team in member_teams:
        if team.id not in all_teams:
            user_member = next((m for m in team.members if m.userId == current_user.id), None)
            all_teams[team.id] = {
                **team.__dict__,
                "memberCount": len(team.members),
                "userRole": user_member.role if user_member else TeamMemberRole.MEMBER
            }
    
    return list(all_teams.values())


@router.post("/", response_model=Team, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new team"""
    
    # Check if user already has a team with this name
    existing_team = await prisma.team.find_first(
        where={
            "ownerId": current_user.id,
            "name": team_data.name
        }
    )
    
    if existing_team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a team with this name"
        )
    
    # Create the team
    team = await prisma.team.create(
        data={
            "name": team_data.name,
            "description": team_data.description,
            "ownerId": current_user.id
        }
    )
    
    logger.info(f"User {current_user.id} created team {team.id}: {team.name}")
    
    return {
        **team.__dict__,
        "memberCount": 0,
        "userRole": TeamMemberRole.OWNER
    }


@router.get("/{team_id}", response_model=Team)
async def get_team(
    team_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get team details"""
    
    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {"members": {"some": {"userId": current_user.id}}}
            ]
        },
        include={
            "members": {
                "include": {
                    "user": True
                }
            }
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    # Determine user's role
    user_role = TeamMemberRole.OWNER if team.ownerId == current_user.id else TeamMemberRole.MEMBER
    if team.ownerId != current_user.id:
        user_member = next((m for m in team.members if m.userId == current_user.id), None)
        if user_member:
            user_role = user_member.role
    
    return {
        **team.__dict__,
        "memberCount": len(team.members),
        "userRole": user_role
    }


@router.put("/{team_id}", response_model=Team)
async def update_team(
    team_id: str,
    team_data: TeamUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update team details (only owner or admin can update)"""
    
    # Check if user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]}
                        }
                    }
                }
            ]
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions"
        )
    
    # Prepare update data
    update_data = {}
    if team_data.name is not None:
        update_data["name"] = team_data.name
    if team_data.description is not None:
        update_data["description"] = team_data.description
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    # Update team
    updated_team = await prisma.team.update(
        where={"id": team_id},
        data=update_data
    )
    
    # Get member count
    member_count = await prisma.teammember.count(
        where={"teamId": team_id}
    )
    
    user_role = TeamMemberRole.OWNER if updated_team.ownerId == current_user.id else TeamMemberRole.ADMIN
    
    logger.info(f"Team {team_id} updated by user {current_user.id}")
    
    return {
        **updated_team.__dict__,
        "memberCount": member_count,
        "userRole": user_role
    }


@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete team (only owner can delete)"""
    
    # Check if user is the owner of this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "ownerId": current_user.id
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner"
        )
    
    # Check if team has projects
    project_count = await prisma.project.count(
        where={"teamId": team_id}
    )
    
    if project_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete team with {project_count} projects. Move or delete projects first."
        )
    
    # Delete team (this will cascade delete members and invitations)
    await prisma.team.delete(where={"id": team_id})
    
    logger.info(f"Team {team_id} deleted by owner {current_user.id}")
    
    return {"message": "Team deleted successfully"}


@router.get("/{team_id}/members", response_model=List[TeamMember])
async def get_team_members(
    team_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get team members"""
    
    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {"members": {"some": {"userId": current_user.id}}}
            ]
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    # Get team members
    members = await prisma.teammember.find_many(
        where={"teamId": team_id},
        include={
            "user": True
        }
    )
    
    return members


@router.post("/{team_id}/members")
async def add_team_member(
    team_id: str,
    member_data: TeamMemberAdd,
    current_user: User = Depends(get_current_user)
):
    """Add a user to the team by GitHub username"""
    
    # Check if user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]}
                        }
                    }
                }
            ]
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions"
        )
    
    # Get the current user's GitHub access token
    access_token = await github_user_service.get_user_github_access_token(current_user.id)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub access token not found. Please re-authenticate with GitHub."
        )
    
    # Find or create user by GitHub username
    user_id = await github_user_service.find_or_create_user_by_github_username(
        member_data.github_username, 
        access_token
    )
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub user '{member_data.github_username}' not found"
        )
    
    # Check if user is already a member
    existing_member = await prisma.teammember.find_first(
        where={
            "teamId": team_id,
            "userId": user_id
        }
    )
    
    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team"
        )
    
    # Add user to team
    team_member = await prisma.teammember.create(
        data={
            "teamId": team_id,
            "userId": user_id,
            "role": member_data.role
        },
        include={
            "user": True
        }
    )
    
    logger.info(f"User {member_data.github_username} (ID: {user_id}) added to team {team_id} by {current_user.id}")
    
    return {
        **team_member.__dict__,
        "user": {
            "id": team_member.user.id,
            "name": team_member.user.name,
            "email": team_member.user.email,
            "image": team_member.user.image,
            "githubId": team_member.user.githubId
        }
    }



@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove a member from the team"""
    
    # Check if current user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]}
                        }
                    }
                }
            ]
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions"
        )
    
    # Cannot remove the team owner
    if user_id == team.ownerId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the team owner"
        )
    
    # Find the member to remove
    member = await prisma.teammember.find_first(
        where={
            "teamId": team_id,
            "userId": user_id
        }
    )
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this team"
        )
    
    # Remove the member
    await prisma.teammember.delete(where={"id": member.id})
    
    logger.info(f"User {user_id} removed from team {team_id} by {current_user.id}")
    
    return {"message": "Member removed successfully"}


@router.put("/{team_id}/members/{user_id}/role")
async def update_member_role(
    team_id: str,
    user_id: str,
    role_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update a team member's role"""
    
    new_role = role_data.get("role")
    if new_role not in [role.value for role in TeamMemberRole]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role"
        )
    
    # Check if current user is the team owner
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "ownerId": current_user.id
        }
    )
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner"
        )
    
    # Cannot change owner role
    if user_id == team.ownerId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the owner's role"
        )
    
    # Find the member
    member = await prisma.teammember.find_first(
        where={
            "teamId": team_id,
            "userId": user_id
        }
    )
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this team"
        )
    
    # Update the role
    updated_member = await prisma.teammember.update(
        where={"id": member.id},
        data={"role": new_role}
    )
    
    logger.info(f"User {user_id} role updated to {new_role} in team {team_id} by {current_user.id}")
    
    return {"message": f"Member role updated to {new_role}"}
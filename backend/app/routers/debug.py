from fastapi import APIRouter, Depends
import logging

from core.database import get_async_session
from core.security import get_current_user
from sqlmodel import select
from models.user import User
from models.project import Project
from models.team import Team, TeamMember
from schemas import User as UserSchema

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users")
async def debug_users():
    """Debug: Get all users in database"""
    try:
        async with get_async_session() as session:
            users = await session.execute(select(User))
            user_list = [
                {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "githubId": user.github_id,
                    "createdAt": user.created_at,
                }
                for user in users.scalars().all()
            ]
            logger.info(f"Found {len(user_list)} users in database")
            return {"users": user_list, "count": len(user_list)}
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        return {"error": str(e)}


@router.get("/projects")
async def debug_projects():
    """Debug: Get all projects in database"""
    try:
        async with get_async_session() as session:
            projects = await session.execute(select(Project))
            project_list = [
                {
                    "id": project.id,
                    "name": project.name,
                    "teamId": project.team_id,
                    "gitRepoUrl": project.git_repo_url,
                    "createdAt": project.created_at,
                }
                for project in projects.scalars().all()
            ]
            logger.info(f"Found {len(project_list)} projects in database")
            return {"projects": project_list, "count": len(project_list)}
    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        return {"error": str(e)}


@router.get("/current-user-projects")
async def debug_current_user_projects(current_user: UserSchema = Depends(get_current_user)):
    """Debug: Get projects for current user"""
    try:
        async with get_async_session() as session:
            # Get team IDs where user is owner or member
            owned_teams = await session.execute(
                select(Team.id).where(Team.owner_id == current_user.id)
            )
            member_teams = await session.execute(
                select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
            )
            
            accessible_team_ids = list(owned_teams.scalars().all()) + list(member_teams.scalars().all())
            
            if accessible_team_ids:
                projects = await session.execute(
                    select(Project).where(Project.team_id.in_(accessible_team_ids))
                )
                project_list = [
                    {
                        "id": project.id,
                        "name": project.name,
                        "teamId": project.team_id,
                        "gitRepoUrl": project.git_repo_url,
                        "createdAt": project.created_at,
                    }
                    for project in projects.scalars().all()
                ]
            else:
                project_list = []
                
            logger.info(f"Found {len(project_list)} projects for user {current_user.id}")
            return {
                "user": {
                    "id": current_user.id,
                    "email": current_user.email,
                    "name": current_user.name,
                },
                "projects": project_list,
                "count": len(project_list),
            }
    except Exception as e:
        logger.error(f"Error fetching projects for user {current_user.id}: {e}")
        return {"error": str(e)}

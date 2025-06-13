from fastapi import APIRouter, Depends
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/users")
async def debug_users():
    """Debug: Get all users in database"""
    try:
        users = await prisma.user.find_many(
            select={
                "id": True,
                "email": True,
                "name": True,
                "githubId": True,
                "createdAt": True
            }
        )
        logger.info(f"Found {len(users)} users in database")
        return {"users": users, "count": len(users)}
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        return {"error": str(e)}


@router.get("/projects")
async def debug_projects():
    """Debug: Get all projects in database"""
    try:
        projects = await prisma.project.find_many(
            select={
                "id": True,
                "name": True,
                "userId": True,
                "gitRepoUrl": True,
                "createdAt": True
            }
        )
        logger.info(f"Found {len(projects)} projects in database")
        return {"projects": projects, "count": len(projects)}
    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        return {"error": str(e)}


@router.get("/current-user-projects")
async def debug_current_user_projects(current_user: User = Depends(get_current_user)):
    """Debug: Get projects for current user"""
    try:
        projects = await prisma.project.find_many(
            where={"userId": current_user.id},
            select={
                "id": True,
                "name": True,
                "userId": True,
                "gitRepoUrl": True,
                "createdAt": True
            }
        )
        logger.info(f"Found {len(projects)} projects for user {current_user.id}")
        return {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "name": current_user.name
            },
            "projects": projects,
            "count": len(projects)
        }
    except Exception as e:
        logger.error(f"Error fetching projects for user {current_user.id}: {e}")
        return {"error": str(e)}
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import boto3
import json
import logging

from core.database import get_async_session
from core.security import get_current_user
from core.config import settings
from sqlmodel import select, and_
from models.project import Project
from models.team import Team, TeamMember, TeamAwsConfig
from models.environment import Environment, EnvironmentVariable as EnvVarModel
from schemas import (
    EnvironmentVariable,
    EnvironmentVariableCreate,
    EnvironmentVariableUpdate,
    User,
)
from services.encryption_service import encryption_service

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_project_aws_credentials(project) -> dict:
    """Get AWS credentials for a project - all projects belong to teams"""
    async with get_async_session() as session:
        try:
            team_aws_config = await session.execute(
                select(TeamAwsConfig).where(
                    and_(TeamAwsConfig.team_id == project.team_id, TeamAwsConfig.is_active == True)
                )
            )
            result = team_aws_config.first()

            if result:
                config = result[0]  # Extract the actual TeamAwsConfig object from the Row
                # Decrypt team credentials
                access_key = encryption_service.decrypt(config.aws_access_key_id)
                secret_key = encryption_service.decrypt(config.aws_secret_access_key)

            if access_key and secret_key:
                    return {
                        "access_key": access_key,
                        "secret_key": secret_key,
                        "region": config.aws_region,
                        "source": "team",
                    }

            # No team credentials configured
            logger.error(f"Project {project.id} has no team AWS credentials configured")
            return None

        except Exception as e:
            logger.error(
                f"Failed to get team AWS credentials for project {project.id}: {e}"
            )
            return None


async def create_aws_client(project, service: str, region: str = None):
    """Create AWS client with appropriate project credentials"""
    from utils.aws_client import create_client
    
    if region is None:
        region = settings.aws_region

    project_credentials = await get_project_aws_credentials(project)

    # Use project's preferred region if different
    if project_credentials and project_credentials["region"] != region:
        region = project_credentials["region"]

    # Convert to format expected by our create_client function
    aws_credentials = None
    if project_credentials:
        aws_credentials = {
            "access_key": project_credentials["access_key"],
            "secret_key": project_credentials["secret_key"],
        }

    return create_client(service, region, aws_credentials)


async def verify_project_access(project_id: str, user_id: str):
    """Verify that the user has access to the project through team membership"""
    async with get_async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Check if user owns team or is a member
        has_access = team.owner_id == user_id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == user_id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        return project


@router.get("/", response_model=List[EnvironmentVariable])
async def get_environment_variables(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get all environment variables for an environment"""
    async with get_async_session() as session:
        # Get the environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project and team
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify user has access to the project through team membership
        has_access = team.owner_id == current_user.id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        env_vars = await session.execute(
            select(EnvVarModel).where(EnvVarModel.environment_id == environment_id)
            .order_by(EnvVarModel.key.asc())
        )

        return env_vars.scalars().all()


@router.post(
    "/", response_model=EnvironmentVariable, status_code=status.HTTP_201_CREATED
)
async def create_environment_variable(
    environment_id: str,
    env_var: EnvironmentVariableCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new environment variable"""
    async with get_async_session() as session:
        # Get the environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project and team
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify user has access to the project through team membership
        has_access = team.owner_id == current_user.id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Check if key already exists in this environment
        existing = await session.execute(
            select(EnvVarModel).where(
                and_(EnvVarModel.environment_id == environment_id, EnvVarModel.key == env_var.key)
            )
        )

        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Environment variable with key '{env_var.key}' already exists",
            )

        # Handle secret storage if needed
        secret_key = None
        if env_var.is_secret and env_var.value:
            secret_key = await store_secret(environment_id, env_var.key, env_var.value, project)

        # Create environment variable
        new_env_var = EnvVarModel(
            environment_id=environment_id,
            project_id=project.id,
            key=env_var.key,
            value=None if env_var.is_secret else env_var.value,
            is_secret=env_var.is_secret,
            secret_key=secret_key,
        )
        session.add(new_env_var)
        await session.commit()
        await session.refresh(new_env_var)

        return new_env_var


@router.put("/{env_var_id}", response_model=EnvironmentVariable)
async def update_environment_variable(
    environment_id: str,
    env_var_id: str,
    env_var_update: EnvironmentVariableUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update an environment variable"""
    async with get_async_session() as session:
        # Get the environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project and team
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify user has access to the project through team membership
        has_access = team.owner_id == current_user.id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Get existing variable
        existing = await session.execute(
            select(EnvVarModel).where(
                and_(EnvVarModel.id == env_var_id, EnvVarModel.environment_id == environment_id)
            )
        )
        existing_var = existing.scalar_one_or_none()

        if not existing_var:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Environment variable not found",
            )

        # Handle value update
        if env_var_update.value is not None:
            if env_var_update.is_secret or existing_var.is_secret:
                # Store as secret
                secret_key = await store_secret(
                    environment_id, existing_var.key, env_var_update.value, project
                )
                existing_var.value = None
                existing_var.secret_key = secret_key
                existing_var.is_secret = True
            else:
                existing_var.value = env_var_update.value
                existing_var.secret_key = None

        if env_var_update.is_secret is not None:
            existing_var.is_secret = env_var_update.is_secret

        session.add(existing_var)
        await session.commit()
        await session.refresh(existing_var)

        return existing_var


@router.delete("/{env_var_id}")
async def delete_environment_variable(
    environment_id: str, env_var_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an environment variable"""
    async with get_async_session() as session:
        # Get the environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project and team
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify user has access to the project through team membership
        has_access = team.owner_id == current_user.id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Get existing variable
        existing = await session.execute(
            select(EnvVarModel).where(
                and_(EnvVarModel.id == env_var_id, EnvVarModel.environment_id == environment_id)
            )
        )
        existing_var = existing.scalar_one_or_none()

        if not existing_var:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Environment variable not found",
            )

        # Delete from Secrets Manager if it's a secret
        if existing_var.is_secret and existing_var.secret_key:
            await delete_secret(existing_var.secret_key, project)

        # Delete the variable
        await session.delete(existing_var)
        await session.commit()

        return {"message": "Environment variable deleted successfully"}


async def store_secret(environment_id: str, key: str, value: str, project) -> str:
    """Store a secret in AWS Secrets Manager"""
    # Project is already passed, no need to fetch it

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    client = await create_aws_client(project, "secretsmanager", settings.aws_region)
    # Include environment ID in secret name to make it unique per environment
    secret_name = f"autoform/{project.name}/{environment_id}/{key}"

    try:
        # Try to create the secret
        response = client.create_secret(
            Name=secret_name,
            SecretString=value,
            Tags=[
                {"Key": "ProjectId", "Value": project.id},
                {"Key": "ProjectName", "Value": project.name},
                {"Key": "EnvironmentId", "Value": environment_id},
                {"Key": "Key", "Value": key},
            ],
        )
        return secret_name
    except client.exceptions.ResourceExistsException:
        # Secret already exists, update it
        client.update_secret(SecretId=secret_name, SecretString=value)
        return secret_name
    except Exception as e:
        logger.error(f"Failed to store secret: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store secret",
        )


async def delete_secret(secret_name: str, project):
    """Delete a secret from AWS Secrets Manager"""
    client = await create_aws_client(project, "secretsmanager", settings.aws_region)

    try:
        client.delete_secret(SecretId=secret_name, ForceDeleteWithoutRecovery=True)
    except client.exceptions.ResourceNotFoundException:
        # Secret doesn't exist, that's fine
        pass
    except Exception as e:
        logger.error(f"Failed to delete secret: {str(e)}")
        # Don't fail the deletion if we can't delete the secret

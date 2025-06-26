from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import boto3
import json
import logging

from core.database import prisma
from core.security import get_current_user
from core.config import settings
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

    try:
        team_aws_config = await prisma.teamawsconfig.find_first(
            where={"teamId": project.teamId, "isActive": True}
        )

        if team_aws_config:
            # Decrypt team credentials
            access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)

            if access_key and secret_key:
                return {
                    "access_key": access_key,
                    "secret_key": secret_key,
                    "region": team_aws_config.awsRegion,
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
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "team": {
                "OR": [
                    {"ownerId": user_id},  # User owns the team
                    {"members": {"some": {"userId": user_id}}}  # User is a team member
                ]
            }
        },
        include={"team": True}
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    return project


@router.get("/", response_model=List[EnvironmentVariable])
async def get_environment_variables(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get all environment variables for an environment"""
    # Get the environment and verify access through the project
    environment = await prisma.environment.find_unique(
        where={"id": environment_id},
        include={"project": {"include": {"team": True}}}
    )
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )
    
    # Verify user has access to the project through team membership
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(
            where={"teamId": project.teamId, "userId": current_user.id}
        )
    )
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    env_vars = await prisma.environmentvariable.find_many(
        where={"environmentId": environment_id}, order={"key": "asc"}
    )

    return env_vars


@router.post(
    "/", response_model=EnvironmentVariable, status_code=status.HTTP_201_CREATED
)
async def create_environment_variable(
    environment_id: str,
    env_var: EnvironmentVariableCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new environment variable"""
    # Get the environment and verify access through the project
    environment = await prisma.environment.find_unique(
        where={"id": environment_id},
        include={"project": {"include": {"team": True}}}
    )
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )
    
    # Verify user has access to the project through team membership
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(
            where={"teamId": project.teamId, "userId": current_user.id}
        )
    )
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Check if key already exists in this environment
    existing = await prisma.environmentvariable.find_first(
        where={"environmentId": environment_id, "key": env_var.key}
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Environment variable with key '{env_var.key}' already exists",
        )

    # Handle secret storage if needed
    secret_key = None
    if env_var.is_secret and env_var.value:
        secret_key = await store_secret(environment_id, env_var.key, env_var.value, project)

    # Create environment variable
    new_env_var = await prisma.environmentvariable.create(
        data={
            "environmentId": environment_id,
            "projectId": project.id,
            "key": env_var.key,
            "value": None if env_var.is_secret else env_var.value,
            "isSecret": env_var.is_secret,
            "secretKey": secret_key,
        }
    )

    return new_env_var


@router.put("/{env_var_id}", response_model=EnvironmentVariable)
async def update_environment_variable(
    environment_id: str,
    env_var_id: str,
    env_var_update: EnvironmentVariableUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update an environment variable"""
    # Get the environment and verify access through the project
    environment = await prisma.environment.find_unique(
        where={"id": environment_id},
        include={"project": {"include": {"team": True}}}
    )
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )
    
    # Verify user has access to the project through team membership
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(
            where={"teamId": project.teamId, "userId": current_user.id}
        )
    )
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Get existing variable
    existing = await prisma.environmentvariable.find_first(
        where={"id": env_var_id, "environmentId": environment_id}
    )

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment variable not found",
        )

    update_data = {}

    # Handle value update
    if env_var_update.value is not None:
        if env_var_update.is_secret or existing.isSecret:
            # Store as secret
            secret_key = await store_secret(
                environment_id, existing.key, env_var_update.value, project
            )
            update_data["value"] = None
            update_data["secretKey"] = secret_key
            update_data["isSecret"] = True
        else:
            update_data["value"] = env_var_update.value
            update_data["secretKey"] = None

    if env_var_update.is_secret is not None:
        update_data["isSecret"] = env_var_update.is_secret

    # Update the variable
    updated_var = await prisma.environmentvariable.update(
        where={"id": env_var_id}, data=update_data
    )

    return updated_var


@router.delete("/{env_var_id}")
async def delete_environment_variable(
    environment_id: str, env_var_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an environment variable"""
    # Get the environment and verify access through the project
    environment = await prisma.environment.find_unique(
        where={"id": environment_id},
        include={"project": {"include": {"team": True}}}
    )
    
    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )
    
    # Verify user has access to the project through team membership
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(
            where={"teamId": project.teamId, "userId": current_user.id}
        )
    )
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Get existing variable
    existing = await prisma.environmentvariable.find_first(
        where={"id": env_var_id, "environmentId": environment_id}
    )

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment variable not found",
        )

    # Delete from Secrets Manager if it's a secret
    if existing.isSecret and existing.secretKey:
        await delete_secret(existing.secretKey, project)

    # Delete the variable
    await prisma.environmentvariable.delete(where={"id": env_var_id})

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

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import boto3
import json
import logging

from core.database import prisma
from core.security import get_current_user
from core.config import settings
from schemas import EnvironmentVariable, EnvironmentVariableCreate, EnvironmentVariableUpdate, User
from services.encryption_service import encryption_service

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_team_aws_credentials(project) -> dict:
    """Get team AWS credentials if project belongs to a team"""
    if not project.teamId:
        return None
    
    try:
        team_aws_config = await prisma.teamawsconfig.find_first(
            where={"teamId": project.teamId, "isActive": True}
        )
        
        if not team_aws_config:
            return None
        
        # Decrypt credentials
        access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
        secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
        
        if not access_key or not secret_key:
            return None
        
        return {
            "access_key": access_key,
            "secret_key": secret_key,
            "region": team_aws_config.awsRegion
        }
    except Exception as e:
        logger.warning(f"Failed to get team AWS credentials: {e}")
        return None


async def create_aws_client(project, service: str, region: str = None):
    """Create AWS client with team credentials if available"""
    if region is None:
        region = settings.aws_region
    
    team_credentials = await get_team_aws_credentials(project)
    
    client_config = {"region_name": region}
    if team_credentials:
        client_config.update({
            "aws_access_key_id": team_credentials["access_key"],
            "aws_secret_access_key": team_credentials["secret_key"]
        })
        # Use team's preferred region if different
        if team_credentials["region"] != region:
            client_config["region_name"] = team_credentials["region"]
    
    return boto3.client(service, **client_config)


async def verify_project_access(project_id: str, user_id: str):
    """Verify that the user has access to the project"""
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "userId": user_id
        }
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return project


@router.get("/", response_model=List[EnvironmentVariable])
async def get_environment_variables(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all environment variables for a project"""
    await verify_project_access(project_id, current_user.id)
    
    env_vars = await prisma.environmentvariable.find_many(
        where={"projectId": project_id},
        order={"key": "asc"}
    )
    
    return env_vars


@router.post("/", response_model=EnvironmentVariable, status_code=status.HTTP_201_CREATED)
async def create_environment_variable(
    project_id: str,
    env_var: EnvironmentVariableCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new environment variable"""
    project = await verify_project_access(project_id, current_user.id)
    
    # Check if key already exists
    existing = await prisma.environmentvariable.find_first(
        where={
            "projectId": project_id,
            "key": env_var.key
        }
    )
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Environment variable with key '{env_var.key}' already exists"
        )
    
    # Handle secret storage if needed
    secret_key = None
    if env_var.is_secret and env_var.value:
        secret_key = await store_secret(project_id, env_var.key, env_var.value)
    
    # Create environment variable
    new_env_var = await prisma.environmentvariable.create(
        data={
            "projectId": project_id,
            "key": env_var.key,
            "value": None if env_var.is_secret else env_var.value,
            "isSecret": env_var.is_secret,
            "secretKey": secret_key
        }
    )
    
    return new_env_var


@router.put("/{env_var_id}", response_model=EnvironmentVariable)
async def update_environment_variable(
    project_id: str,
    env_var_id: str,
    env_var_update: EnvironmentVariableUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update an environment variable"""
    await verify_project_access(project_id, current_user.id)
    
    # Get existing variable
    existing = await prisma.environmentvariable.find_first(
        where={
            "id": env_var_id,
            "projectId": project_id
        }
    )
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment variable not found"
        )
    
    update_data = {}
    
    # Handle value update
    if env_var_update.value is not None:
        if env_var_update.is_secret or existing.isSecret:
            # Store as secret
            secret_key = await store_secret(project_id, existing.key, env_var_update.value)
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
        where={"id": env_var_id},
        data=update_data
    )
    
    return updated_var


@router.delete("/{env_var_id}")
async def delete_environment_variable(
    project_id: str,
    env_var_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete an environment variable"""
    await verify_project_access(project_id, current_user.id)
    
    # Get existing variable
    existing = await prisma.environmentvariable.find_first(
        where={
            "id": env_var_id,
            "projectId": project_id
        }
    )
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment variable not found"
        )
    
    # Delete from Secrets Manager if it's a secret
    if existing.isSecret and existing.secretKey:
        # Get project info for team credentials
        project = await prisma.project.find_unique(
            where={"id": project_id},
            select={"teamId": True}
        )
        await delete_secret(existing.secretKey, project)
    
    # Delete the variable
    await prisma.environmentvariable.delete(
        where={"id": env_var_id}
    )
    
    return {"message": "Environment variable deleted successfully"}


async def store_secret(project_id: str, key: str, value: str) -> str:
    """Store a secret in AWS Secrets Manager"""
    # Get project name to use in secret path
    project = await prisma.project.find_unique(
        where={"id": project_id},
        select={"name": True, "teamId": True}
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    client = await create_aws_client(project, 'secretsmanager', settings.aws_region)
    secret_name = f"autoform/{project.name}/{key}"
    
    try:
        # Try to create the secret
        response = client.create_secret(
            Name=secret_name,
            SecretString=value,
            Tags=[
                {'Key': 'ProjectId', 'Value': project_id},
                {'Key': 'ProjectName', 'Value': project.name},
                {'Key': 'Key', 'Value': key}
            ]
        )
        return secret_name
    except client.exceptions.ResourceExistsException:
        # Secret already exists, update it
        client.update_secret(
            SecretId=secret_name,
            SecretString=value
        )
        return secret_name
    except Exception as e:
        logger.error(f"Failed to store secret: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store secret"
        )


async def delete_secret(secret_name: str, project):
    """Delete a secret from AWS Secrets Manager"""
    client = await create_aws_client(project, 'secretsmanager', settings.aws_region)
    
    try:
        client.delete_secret(
            SecretId=secret_name,
            ForceDeleteWithoutRecovery=True
        )
    except client.exceptions.ResourceNotFoundException:
        # Secret doesn't exist, that's fine
        pass
    except Exception as e:
        logger.error(f"Failed to delete secret: {str(e)}")
        # Don't fail the deletion if we can't delete the secret
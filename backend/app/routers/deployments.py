from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List
import uuid
from datetime import datetime
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import Deployment, DeploymentStatus, User, ProjectStatus
from services import DeploymentService, DeploymentConfig, deployment_manager, encryption_service
from .github import get_branch_commit_sha

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/deployments", response_model=List[Deployment])
async def get_deployments(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get all deployments for a project"""
    # Verify project belongs to user
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "userId": current_user.id
        }
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    deployments = await prisma.deployment.find_many(
        where={"projectId": project_id},
        order={"createdAt": "desc"}
    )
    
    return deployments


@router.post("/projects/{project_id}/deploy")
async def deploy_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Start a new deployment for a project"""
    # Get project with team info
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "OR": [
                {"userId": current_user.id},  # User owns the project
                {
                    "team": {
                        "OR": [
                            {"ownerId": current_user.id},  # User owns the team
                            {"members": {"some": {"userId": current_user.id}}}  # User is team member
                        ]
                    }
                }
            ]
        },
        include={
            "team": True
        }
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check if there's already an active deployment
    active_deployment = await prisma.deployment.find_first(
        where={
            "projectId": project_id,
            "status": {"in": [
                DeploymentStatus.PENDING,
                DeploymentStatus.BUILDING,
                DeploymentStatus.PUSHING,
                DeploymentStatus.PROVISIONING,
                DeploymentStatus.DEPLOYING
            ]}
        }
    )
    
    if active_deployment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There is already an active deployment for this project"
        )
    
    # Get the actual commit SHA from GitHub
    try:
        commit_sha = await get_branch_commit_sha(
            project.gitRepoUrl,
            project.branch or "main",
            current_user
        )
        logger.info(f"Retrieved commit SHA: {commit_sha} for branch: {project.branch or 'main'}")
    except Exception as e:
        logger.warning(f"Failed to get commit SHA: {e}. Using fallback.")
        # Fallback to timestamp-based SHA if GitHub API fails
        commit_sha = f"deploy-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    # Create deployment record
    deployment = await prisma.deployment.create(
        data={
            "projectId": project_id,
            "status": DeploymentStatus.PENDING,
            "imageTag": f"{project.name}:{commit_sha}",
            "commitSha": commit_sha
        }
    )
    
    # Update project status
    await prisma.project.update(
        where={"id": project_id},
        data={"status": ProjectStatus.DEPLOYING}
    )
    
    # Check for team AWS credentials if this is a team project
    aws_credentials = None
    aws_region = None
    
    if project.teamId:
        # Get team AWS config
        team_aws_config = await prisma.teamawsconfig.find_first(
            where={"teamId": project.teamId, "isActive": True}
        )
        
        if team_aws_config:
            # Decrypt credentials
            access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
            
            if access_key and secret_key:
                aws_credentials = {
                    "access_key": access_key,
                    "secret_key": secret_key
                }
                aws_region = team_aws_config.awsRegion
                logger.info(f"Using team AWS credentials for project {project_id}")
    
    # Start deployment in background
    deployment_service = DeploymentService(region=aws_region, aws_credentials=aws_credentials)
    
    # Create deployment configuration
    config = DeploymentConfig(
        project_id=project_id,
        project_name=project.name,
        git_repo_url=project.gitRepoUrl,
        branch=project.branch or "main",
        commit_sha=commit_sha,
        subdirectory=project.subdirectory,
        health_check_path=project.healthCheckPath or "/",
        port=project.port or 3000,
        cpu=project.cpu or 256,
        memory=project.memory or 512,
        disk_size=project.diskSize or 21
    )
    
    background_tasks.add_task(
        deployment_service.deploy_project,
        config=config,
        deployment_id=deployment.id
    )
    
    return {
        "message": "Deployment started",
        "deploymentId": deployment.id
    }


@router.post("/projects/{project_id}/abort")
async def abort_deployment(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Abort the current deployment"""
    # Verify project belongs to user
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "userId": current_user.id
        }
    )
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Find active deployment
    active_deployment = await prisma.deployment.find_first(
        where={
            "projectId": project_id,
            "status": {"in": [
                DeploymentStatus.PENDING,
                DeploymentStatus.BUILDING,
                DeploymentStatus.PUSHING,
                DeploymentStatus.PROVISIONING,
                DeploymentStatus.DEPLOYING
            ]}
        }
    )
    
    if not active_deployment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active deployment found"
        )
    
    # Update deployment status
    await prisma.deployment.update(
        where={"id": active_deployment.id},
        data={
            "status": DeploymentStatus.FAILED,
            "logs": (active_deployment.logs or "") + "\n[ABORTED] Deployment aborted by user"
        }
    )
    
    # Update project status
    await prisma.project.update(
        where={"id": project_id},
        data={"status": ProjectStatus.FAILED}
    )
    
    # Abort the deployment process
    deployment_manager.abort_deployment(project_id)
    
    return {"message": "Deployment aborted"}


@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get logs for a specific deployment"""
    # Get deployment and verify access
    deployment = await prisma.deployment.find_unique(
        where={"id": deployment_id},
        include={"project": True}
    )
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )
    
    if deployment.project.userId != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return {
        "logs": deployment.logs or "",
        "status": deployment.status
    }
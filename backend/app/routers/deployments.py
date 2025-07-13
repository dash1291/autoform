from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import uuid
from datetime import datetime, timedelta
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import Deployment, DeploymentStatus, User, ProjectStatus
from services import (
    DeploymentConfig,
    deployment_manager,
    encryption_service,
)
from .github import get_branch_commit_sha
from app.workers.tasks import deploy_project as deploy_project_task, abort_deployment as abort_deployment_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/deployments")
async def get_deployments(
    project_id: str, current_user: User = Depends(get_current_user)
):
    """Get all deployments for a project"""
    # Verify project access (all projects belong to teams)
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "team": {
                "OR": [
                    {"ownerId": current_user.id},  # User owns the team
                    {
                        "members": {"some": {"userId": current_user.id}}
                    },  # User is team member
                ]
            },
        },
        include={"team": True},
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    deployments = await prisma.deployment.find_many(
        where={"projectId": project_id}, 
        order={"createdAt": "desc"},
        include={"environment": True}
    )

    # Format the response to ensure all fields are included
    deployment_list = []
    for deployment in deployments:
        # Debug log
        logger.info(f"Deployment {deployment.id} has logs: {bool(deployment.logs)}, logs length: {len(deployment.logs) if deployment.logs else 0}")
        
        deployment_data = {
            "id": deployment.id,
            "projectId": deployment.projectId,
            "environmentId": deployment.environmentId if hasattr(deployment, 'environmentId') else None,
            "status": deployment.status,
            "imageTag": deployment.imageTag,
            "commitSha": deployment.commitSha,
            "logs": deployment.logs,
            "details": deployment.details if deployment.details else None,
            "createdAt": deployment.createdAt.isoformat() if deployment.createdAt else None,
            "updatedAt": deployment.updatedAt.isoformat() if deployment.updatedAt else None,
        }
        if hasattr(deployment, 'environment') and deployment.environment:
            deployment_data["environment"] = {
                "id": deployment.environment.id,
                "name": deployment.environment.name,
            }
        deployment_list.append(deployment_data)

    return deployment_list


@router.post("/environments/{environment_id}/deploy")
async def deploy_environment(
    environment_id: str,
    current_user: User = Depends(get_current_user),
):
    """Start a new deployment for an environment"""
    # Get environment with project and team info
    environment = await prisma.environment.find_first(
        where={"id": environment_id},
        include={
            "project": {"include": {"team": True}},
            "teamAwsConfig": True,
        },
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Verify access to the project (all projects belong to teams)
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

    # Check if there's already an active deployment for this environment
    active_deployment = await prisma.deployment.find_first(
        where={
            "environmentId": environment_id,
            "status": {
                "in": [
                    DeploymentStatus.PENDING,
                    DeploymentStatus.BUILDING,
                    DeploymentStatus.PUSHING,
                    DeploymentStatus.PROVISIONING,
                    DeploymentStatus.DEPLOYING,
                ]
            },
        }
    )

    if active_deployment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="There is already an active deployment for this environment",
        )

    # Get the actual commit SHA from GitHub
    try:
        commit_sha = await get_branch_commit_sha(
            project.gitRepoUrl, environment.branch or "main", current_user
        )
        logger.info(
            f"Retrieved commit SHA: {commit_sha} for branch: {environment.branch or 'main'}"
        )
    except Exception as e:
        logger.warning(f"Failed to get commit SHA: {e}. Using fallback.")
        # Fallback to timestamp-based SHA if GitHub API fails
        commit_sha = f"deploy-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Create deployment record
    deployment = await prisma.deployment.create(
        data={
            "projectId": project.id,
            "environmentId": environment_id,
            "status": DeploymentStatus.PENDING,
            "imageTag": f"{project.name}-{environment.name}:{commit_sha}",
            "commitSha": commit_sha,
        }
    )

    # Update environment status
    await prisma.environment.update(
        where={"id": environment_id}, data={"status": ProjectStatus.DEPLOYING}
    )

    # Get environment's specific AWS credentials
    team_aws_config = environment.teamAwsConfig

    if not team_aws_config:
        logger.error(f"Environment {environment_id} has no AWS credentials configured")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No AWS credentials configured for this environment",
        )

    # Decrypt team credentials
    access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
    secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)

    if not access_key or not secret_key:
        logger.error(f"Environment {environment_id} has invalid AWS credentials")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AWS credentials are not properly configured",
        )

    aws_credentials = {"access_key": access_key, "secret_key": secret_key}
    aws_region = team_aws_config.awsRegion
    logger.info(f"Using AWS credentials '{team_aws_config.name}' for environment {environment_id}")

    # Create deployment configuration
    config = DeploymentConfig(
        project_id=project.id,
        project_name=f"{project.name[:23] if len(f'{project.name}-{environment.name}') > 32 else project.name}-{environment.name[:8] if len(f'{project.name}-{environment.name}') > 32 else environment.name}",
        git_repo_url=project.gitRepoUrl,
        branch=environment.branch or "main",
        commit_sha=commit_sha,
        environment_id=environment_id,
        subdirectory=project.subdirectory,
        health_check_path=project.healthCheckPath or "/",
        port=environment.project.port or 3000,
        cpu=environment.cpu or 256,
        memory=environment.memory or 512,
        disk_size=environment.diskSize or 21,
        aws_region=aws_region,
        aws_credentials=aws_credentials
    )

    # Queue deployment task with Celery using apply_async for better control
    task = deploy_project_task.apply_async(
        kwargs={
            "config": config.dict(), 
            "deployment_id": deployment.id
        },
        queue="deployments",
        retry=False
    )
    
    # Save the Celery task ID to the deployment record immediately
    await prisma.deployment.update(
        where={"id": deployment.id},
        data={"celeryTaskId": task.id}
    )

    return {"message": "Deployment started", "deploymentId": deployment.id}


@router.post("/{deployment_id}/abort")
async def abort_deployment(
    deployment_id: str, current_user: User = Depends(get_current_user)
):
    """Abort a specific deployment"""
    # Get deployment and verify access
    deployment = await prisma.deployment.find_unique(
        where={"id": deployment_id}, include={"project": {"include": {"team": True}}}
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
        )

    # Verify user has access to the project (all projects belong to teams)
    team_access = (
        deployment.project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={"teamId": deployment.project.teamId, "userId": current_user.id}
        )  # User is team member
    )

    if not team_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Check if deployment can be aborted
    if deployment.status not in [
        DeploymentStatus.PENDING,
        DeploymentStatus.BUILDING,
        DeploymentStatus.PUSHING,
        DeploymentStatus.PROVISIONING,
        DeploymentStatus.DEPLOYING,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot abort deployment with status: {deployment.status}",
        )

    # Update deployment status immediately
    await prisma.deployment.update(
        where={"id": deployment_id},
        data={
            "status": DeploymentStatus.FAILED,
            "logs": (deployment.logs or "") + "\n[ABORTED] Deployment aborted by user",
        },
    )

    # Update environment status if this was the active deployment for the environment
    if deployment.environmentId:
        # Check if there are any other active deployments for this environment
        active_deployment = await prisma.deployment.find_first(
            where={
                "environmentId": deployment.environmentId,
                "id": {"not": deployment_id},  # Exclude the current deployment
                "status": {
                    "in": [
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]
                },
            },
            order={"createdAt": "desc"},
        )

        # If no other active deployments, update environment status
        if not active_deployment:
            await prisma.environment.update(
                where={"id": deployment.environmentId}, 
                data={"status": ProjectStatus.FAILED}
            )

    # Revoke the celery task if it exists
    if deployment.celeryTaskId:
        from app.workers.celery_app import app
        app.control.revoke(deployment.celeryTaskId, terminate=True)

    # Also try to abort using deployment manager
    try:
        from services.deployment_manager import deployment_manager
        deployment_manager.abort_deployment_by_id(deployment_id, deployment.projectId)
    except:
        pass  # Ignore errors from deployment manager

    return {"message": "Deployment aborted"}


@router.post("/admin/fix-stuck-environments")
async def fix_stuck_environments(
    current_user: User = Depends(get_current_user)
):
    """Fix environments stuck in deploying status (Admin only)"""
    # For now, allow any authenticated user to run this
    # In production, you'd want to check if user is admin
    
    # Find environments stuck in DEPLOYING status
    stuck_environments = await prisma.environment.find_many(
        where={"status": "DEPLOYING"},
        include={"deployments": True}
    )
    
    fixed_environments = []
    
    for environment in stuck_environments:
        # Check if there are any active deployments for this environment
        active_deployment = await prisma.deployment.find_first(
            where={
                "environmentId": environment.id,
                "status": {
                    "in": [
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]
                }
            }
        )
        
        if not active_deployment:
            # No active deployments, so reset environment status
            await prisma.environment.update(
                where={"id": environment.id},
                data={"status": "CREATED"}
            )
            fixed_environments.append(environment.id)
    
    return {
        "message": "Fixed stuck environments",
        "fixed_environments": len(fixed_environments),
        "environment_ids": fixed_environments
    }


@router.post("/admin/fix-stuck-deployments")
async def fix_stuck_deployments(
    current_user: User = Depends(get_current_user),
    cutoff_minutes: int = 30
):
    """Fix deployments and environments stuck in deploying status (Admin only)"""
    # For now, allow any authenticated user to run this
    # In production, you'd want to check if user is admin
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=cutoff_minutes)
    
    # Find stuck deployments
    stuck_deployments = await prisma.deployment.find_many(
        where={
            "status": {
                "in": [
                    DeploymentStatus.PENDING,
                    DeploymentStatus.BUILDING,
                    DeploymentStatus.PUSHING,
                    DeploymentStatus.PROVISIONING,
                    DeploymentStatus.DEPLOYING,
                ]
            },
            "createdAt": {"lt": cutoff_time}
        },
        include={"environment": True}
    )
    
    fixed_deployments = []
    
    for deployment in stuck_deployments:
        # Update deployment to failed
        await prisma.deployment.update(
            where={"id": deployment.id},
            data={
                "status": DeploymentStatus.FAILED,
                "logs": (deployment.logs or "") + "\n[SYSTEM] Deployment timed out and was marked as failed"
            }
        )
        
        fixed_deployments.append(deployment.id)
        
        # Update environment status if needed
        if deployment.environmentId and deployment.environment:
            # Check if there are any other active deployments
            active_deployment = await prisma.deployment.find_first(
                where={
                    "environmentId": deployment.environmentId,
                    "id": {"not": deployment.id},
                    "status": {
                        "in": [
                            DeploymentStatus.PENDING,
                            DeploymentStatus.BUILDING,
                            DeploymentStatus.PUSHING,
                            DeploymentStatus.PROVISIONING,
                            DeploymentStatus.DEPLOYING,
                        ]
                    }
                }
            )
            
            if not active_deployment:
                await prisma.environment.update(
                    where={"id": deployment.environmentId},
                    data={"status": ProjectStatus.FAILED}
                )
    
    # Fix stuck environments
    stuck_environments = await prisma.environment.find_many(
        where={
            "status": ProjectStatus.DEPLOYING,
            "updatedAt": {"lt": cutoff_time}
        }
    )
    
    fixed_environments = []
    
    for environment in stuck_environments:
        # Check if there are any active deployments
        active_deployment = await prisma.deployment.find_first(
            where={
                "environmentId": environment.id,
                "status": {
                    "in": [
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]
                }
            }
        )
        
        if not active_deployment:
            await prisma.environment.update(
                where={"id": environment.id},
                data={"status": ProjectStatus.FAILED}
            )
            fixed_environments.append(environment.id)
    
    return {
        "message": "Fixed stuck deployments and environments",
        "fixed_deployments": len(fixed_deployments),
        "fixed_environments": len(fixed_environments),
        "deployment_ids": fixed_deployments,
        "environment_ids": fixed_environments
    }


@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: str, current_user: User = Depends(get_current_user)
):
    """Get logs for a specific deployment"""
    # Get deployment and verify access
    deployment = await prisma.deployment.find_unique(
        where={"id": deployment_id}, include={"project": {"include": {"team": True}}}
    )

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
        )

    # Verify user has access to the project (all projects belong to teams)
    team_access = (
        deployment.project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={"teamId": deployment.project.teamId, "userId": current_user.id}
        )  # User is team member
    )

    if not team_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    return {"logs": deployment.logs or "", "status": deployment.status}

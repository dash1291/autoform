from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import uuid
from datetime import datetime, timedelta
import logging

from core.database import get_async_session
from core.security import get_current_user
from sqlmodel import select, update
from models.deployment import Deployment, DeploymentStatus
from models.project import Project, ProjectStatus
from models.user import User
from models.team import Team, TeamMember
from models.environment import Environment
from schemas import User as UserSchema
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
    project_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Get all deployments for a project"""
    # Verify project access (all projects belong to teams)
    async with get_async_session() as session:
        # Get project with team
        project_result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        
        if not project or not project.team_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Check team access
        team_result = await session.execute(
            select(Team).where(Team.id == project.team_id)
        )
        team = team_result.scalar_one_or_none()
        
        has_access = False
        if team and team.owner_id == current_user.id:
            has_access = True
        else:
            # Check if user is team member
            member_result = await session.execute(
                select(TeamMember).where(
                    (TeamMember.team_id == project.team_id) & 
                    (TeamMember.user_id == current_user.id)
                )
            )
            if member_result.scalar_one_or_none():
                has_access = True

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Get deployments for this project
        deployments_result = await session.execute(
            select(Deployment).where(Deployment.project_id == project_id)
            .order_by(Deployment.created_at.desc())
        )
        deployments = deployments_result.scalars().all()
        
        # Get environments for deployments that have them
        environments = {}
        for deployment in deployments:
            if deployment.environment_id:
                env_result = await session.execute(
                    select(Environment).where(Environment.id == deployment.environment_id)
                )
                env = env_result.scalar_one_or_none()
                if env:
                    environments[deployment.environment_id] = env

        # Format the response to ensure all fields are included
        deployment_list = []
        for deployment in deployments:
            # Debug log
            logger.info(f"Deployment {deployment.id} has logs: {bool(deployment.logs)}, logs length: {len(deployment.logs) if deployment.logs else 0}")
            
            deployment_data = {
                "id": deployment.id,
                "projectId": deployment.project_id,
                "environmentId": deployment.environment_id,
                "status": deployment.status,
                "imageTag": deployment.image_tag,
                "commitSha": deployment.commit_sha,
                "logs": deployment.logs,
                "details": deployment.details,
                "createdAt": deployment.created_at.isoformat() if deployment.created_at else None,
                "updatedAt": deployment.updated_at.isoformat() if deployment.updated_at else None,
            }
            
            # Add environment info if available
            if deployment.environment_id and deployment.environment_id in environments:
                env = environments[deployment.environment_id]
                deployment_data["environment"] = {
                    "id": env.id,
                    "name": env.name,
                }
            
            deployment_list.append(deployment_data)

        return deployment_list


@router.post("/environments/{environment_id}/deploy")
async def deploy_environment(
    environment_id: str,
    current_user: UserSchema = Depends(get_current_user),
):
    """Start a new deployment for an environment"""
    async with get_async_session() as session:
        # Get environment with project and team info
        environment_result = await session.execute(
            select(Environment).where(Environment.id == environment_id)
        )
        environment = environment_result.scalar_one_or_none()

        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get the associated project and team
        project_result = await session.execute(
            select(Project).where(Project.id == environment.project_id)
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team info
        team_result = await session.execute(
            select(Team).where(Team.id == project.team_id)
        )
        team = team_result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access to the project
        has_access = team.owner_id == current_user.id
        if not has_access:
            # Check if user is team member
            member_result = await session.execute(
                select(TeamMember).where(
                    (TeamMember.team_id == project.team_id) & 
                    (TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        # Check if there's already an active deployment for this environment
        active_result = await session.execute(
            select(Deployment).where(
                (Deployment.environment_id == environment_id) &
                (Deployment.status.in_([
                    DeploymentStatus.PENDING,
                    DeploymentStatus.BUILDING,
                    DeploymentStatus.PUSHING,
                    DeploymentStatus.PROVISIONING,
                    DeploymentStatus.DEPLOYING,
                ]))
            )
        )
        active_deployment = active_result.scalar_one_or_none()

        if active_deployment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="There is already an active deployment for this environment",
            )

        # Get the actual commit SHA from GitHub
        try:
            commit_sha = await get_branch_commit_sha(
                project.git_repo_url, environment.branch or "main", current_user
            )
            logger.info(
                f"Retrieved commit SHA: {commit_sha} for branch: {environment.branch or 'main'}"
            )
        except Exception as e:
            logger.warning(f"Failed to get commit SHA: {e}. Using fallback.")
            # Fallback to timestamp-based SHA if GitHub API fails
            commit_sha = f"deploy-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        # Create deployment record
        from datetime import datetime
        deployment = Deployment(
            project_id=project.id,
            environment_id=environment_id,
            status=DeploymentStatus.PENDING,
            image_tag=f"{project.name}-{environment.name}:{commit_sha}",
            commit_sha=commit_sha,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        session.add(deployment)
        await session.flush()  # Get the deployment ID
        await session.refresh(deployment)

        # Update environment status
        environment.status = ProjectStatus.DEPLOYING
        environment.updated_at = datetime.utcnow()
        session.add(environment)
        await session.commit()

        # Get environment's specific AWS credentials
        from models.team import TeamAwsConfig
        team_aws_config_result = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.id == environment.team_aws_config_id)
        )
        team_aws_config = team_aws_config_result.scalar_one_or_none()

        if not team_aws_config:
            logger.error(f"Environment {environment_id} has no AWS credentials configured")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No AWS credentials configured for this environment",
            )

        # Decrypt team credentials
        access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
        secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)

        if not access_key or not secret_key:
            logger.error(f"Environment {environment_id} has invalid AWS credentials")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS credentials are not properly configured",
            )

        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
        aws_region = team_aws_config.aws_region
        logger.info(f"Using AWS credentials '{team_aws_config.name}' for environment {environment_id}")

        # Create deployment configuration
        config = DeploymentConfig(
            project_id=project.id,
            project_name=f"{project.name[:23] if len(f'{project.name}-{environment.name}') > 32 else project.name}-{environment.name[:8] if len(f'{project.name}-{environment.name}') > 32 else environment.name}",
            git_repo_url=project.git_repo_url,
            branch=environment.branch or "main",
            commit_sha=commit_sha,
            environment_id=environment_id,
            subdirectory=project.subdirectory,
            health_check_path=project.health_check_path or "/",
            port=project.port or 3000,
            cpu=environment.cpu or 256,
            memory=environment.memory or 512,
            disk_size=environment.disk_size or 21,
            desired_instance_count=environment.desired_instance_count if hasattr(environment, 'desired_instance_count') else 1,
            aws_region=aws_region,
            aws_credentials=aws_credentials
        )

        # Queue deployment task with Celery using apply_async for better control
        logger.info(f"Queuing deployment task for deployment {deployment.id}")
        
        try:
            task = deploy_project_task.apply_async(
                kwargs={
                    "config": config.dict(), 
                    "deployment_id": deployment.id
                },
                queue="deployments",
                retry=False
            )
            logger.info(f"Task queued successfully with ID: {task.id}")
        except Exception as e:
            logger.error(f"Failed to queue task: {e}")
            raise
        
        # Save the Celery task ID to the deployment record immediately
        async with get_async_session() as update_session:
            deployment_result = await update_session.execute(
                select(Deployment).where(Deployment.id == deployment.id)
            )
            deployment_to_update = deployment_result.scalar_one_or_none()
            if deployment_to_update:
                deployment_to_update.celery_task_id = task.id
                deployment_to_update.updated_at = datetime.utcnow()
                update_session.add(deployment_to_update)
                await update_session.commit()

        return {"message": "Deployment started", "deploymentId": deployment.id}


@router.post("/{deployment_id}/abort")
async def abort_deployment(
    deployment_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Abort a specific deployment"""
    async with get_async_session() as session:
        # Get deployment and verify access
        deployment_result = await session.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = deployment_result.scalar_one_or_none()

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
            )
        
        # Get project and team info
        project_result = await session.execute(
            select(Project).where(Project.id == deployment.project_id)
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team_result = await session.execute(
            select(Team).where(Team.id == project.team_id)
        )
        team = team_result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )

        # Verify user has access to the project
        team_access = team.owner_id == current_user.id
        if not team_access:
            # Check if user is team member
            member_result = await session.execute(
                select(TeamMember).where(
                    (TeamMember.team_id == project.team_id) & 
                    (TeamMember.user_id == current_user.id)
                )
            )
            team_access = member_result.scalar_one_or_none() is not None

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
        deployment.status = DeploymentStatus.FAILED
        deployment.logs = (deployment.logs or "") + "\n[ABORTED] Deployment aborted by user"
        deployment.updated_at = datetime.utcnow()
        session.add(deployment)
        await session.commit()

        # Update environment status if this was the active deployment for the environment
        if deployment.environment_id:
            # Check if there are any other active deployments for this environment
            active_result = await session.execute(
                select(Deployment).where(
                    (Deployment.environment_id == deployment.environment_id) &
                    (Deployment.id != deployment_id) &
                    (Deployment.status.in_([
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]))
                ).order_by(Deployment.created_at.desc())
            )
            active_deployment = active_result.scalar_one_or_none()

            # If no other active deployments, update environment status
            if not active_deployment:
                env_result = await session.execute(
                    select(Environment).where(Environment.id == deployment.environment_id)
                )
                environment = env_result.scalar_one_or_none()
                if environment:
                    environment.status = ProjectStatus.FAILED
                    environment.updated_at = datetime.utcnow()
                    session.add(environment)
                    await session.commit()

        # Revoke the celery task if it exists
        if deployment.celery_task_id:
            from app.workers.celery_app import app
            app.control.revoke(deployment.celery_task_id, terminate=True)

        # Also try to abort using deployment manager
        try:
            from services.deployment_manager import deployment_manager
            deployment_manager.abort_deployment_by_id(deployment_id, deployment.project_id)
        except:
            pass  # Ignore errors from deployment manager

        return {"message": "Deployment aborted"}


@router.post("/admin/fix-stuck-environments")
async def fix_stuck_environments(
    current_user: UserSchema = Depends(get_current_user)
):
    """Fix environments stuck in deploying status (Admin only)"""
    # For now, allow any authenticated user to run this
    # In production, you'd want to check if user is admin
    
    async with get_async_session() as session:
        # Find environments stuck in DEPLOYING status
        stuck_result = await session.execute(
            select(Environment).where(Environment.status == "DEPLOYING")
        )
        stuck_environments = stuck_result.scalars().all()
        
        fixed_environments = []
        
        for environment in stuck_environments:
            # Check if there are any active deployments for this environment
            active_result = await session.execute(
                select(Deployment).where(
                    (Deployment.environment_id == environment.id) &
                    (Deployment.status.in_([
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]))
                )
            )
            active_deployment = active_result.scalar_one_or_none()
            
            if not active_deployment:
                # No active deployments, so reset environment status
                environment.status = "CREATED"
                environment.updated_at = datetime.utcnow()
                session.add(environment)
                fixed_environments.append(environment.id)
        
        await session.commit()
    
    return {
        "message": "Fixed stuck environments",
        "fixed_environments": len(fixed_environments),
        "environment_ids": fixed_environments
    }


@router.post("/admin/fix-stuck-deployments")
async def fix_stuck_deployments(
    current_user: UserSchema = Depends(get_current_user),
    cutoff_minutes: int = 30
):
    """Fix deployments and environments stuck in deploying status (Admin only)"""
    # For now, allow any authenticated user to run this
    # In production, you'd want to check if user is admin
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=cutoff_minutes)
    
    async with get_async_session() as session:
        # Find stuck deployments
        stuck_result = await session.execute(
            select(Deployment).where(
                (Deployment.status.in_([
                    DeploymentStatus.PENDING,
                    DeploymentStatus.BUILDING,
                    DeploymentStatus.PUSHING,
                    DeploymentStatus.PROVISIONING,
                    DeploymentStatus.DEPLOYING,
                ])) &
                (Deployment.created_at < cutoff_time)
            )
        )
        stuck_deployments = stuck_result.scalars().all()
    
    fixed_deployments = []
    
    for deployment in stuck_deployments:
        # Update deployment to failed
        async with get_async_session() as update_session:
            deployment_result = await update_session.execute(
                select(Deployment).where(Deployment.id == deployment.id)
            )
            deployment_to_update = deployment_result.scalar_one_or_none()
            if deployment_to_update:
                deployment_to_update.status = DeploymentStatus.FAILED
                deployment_to_update.logs = (deployment.logs or "") + "\n[SYSTEM] Deployment timed out and was marked as failed"
                deployment_to_update.updated_at = datetime.utcnow()
                update_session.add(deployment_to_update)
                await update_session.commit()
        
        fixed_deployments.append(deployment.id)
        
        # Update environment status if needed
        if deployment.environment_id:
            # Check if there are any other active deployments
            async with get_async_session() as env_session:
                active_result = await env_session.execute(
                    select(Deployment).where(
                        (Deployment.environment_id == deployment.environment_id) &
                        (Deployment.id != deployment.id) &
                        (Deployment.status.in_([
                            DeploymentStatus.PENDING,
                            DeploymentStatus.BUILDING,
                            DeploymentStatus.PUSHING,
                            DeploymentStatus.PROVISIONING,
                            DeploymentStatus.DEPLOYING,
                        ]))
                    )
                )
                active_deployment = active_result.scalar_one_or_none()
                
                if not active_deployment:
                    env_result = await env_session.execute(
                        select(Environment).where(Environment.id == deployment.environment_id)
                    )
                    environment_to_update = env_result.scalar_one_or_none()
                    if environment_to_update:
                        environment_to_update.status = ProjectStatus.FAILED
                        environment_to_update.updated_at = datetime.utcnow()
                        env_session.add(environment_to_update)
                        await env_session.commit()
    
    # Fix stuck environments
    async with get_async_session() as env_session:
        stuck_env_result = await env_session.execute(
            select(Environment).where(
                (Environment.status == ProjectStatus.DEPLOYING) &
                (Environment.updated_at < cutoff_time)
            )
        )
        stuck_environments = stuck_env_result.scalars().all()
        
        fixed_environments = []
        
        for environment in stuck_environments:
            # Check if there are any active deployments
            active_result = await env_session.execute(
                select(Deployment).where(
                    (Deployment.environment_id == environment.id) &
                    (Deployment.status.in_([
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]))
                )
            )
            active_deployment = active_result.scalar_one_or_none()
            
            if not active_deployment:
                environment.status = ProjectStatus.FAILED
                environment.updated_at = datetime.utcnow()
                env_session.add(environment)
                fixed_environments.append(environment.id)
        
        await env_session.commit()
    
    return {
        "message": "Fixed stuck deployments and environments",
        "fixed_deployments": len(fixed_deployments),
        "fixed_environments": len(fixed_environments),
        "deployment_ids": fixed_deployments,
        "environment_ids": fixed_environments
    }


@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Get logs for a specific deployment"""
    async with get_async_session() as session:
        # Get deployment and verify access
        deployment_result = await session.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = deployment_result.scalar_one_or_none()

        if not deployment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found"
            )

        # Get project and team info
        project_result = await session.execute(
            select(Project).where(Project.id == deployment.project_id)
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        team_result = await session.execute(
            select(Team).where(Team.id == project.team_id)
        )
        team = team_result.scalar_one_or_none()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )

        # Verify user has access to the project (all projects belong to teams)
        team_access = team.owner_id == current_user.id
        if not team_access:
            # Check if user is team member
            member_result = await session.execute(
                select(TeamMember).where(
                    (TeamMember.team_id == project.team_id) &
                    (TeamMember.user_id == current_user.id)
                )
            )
            team_access = member_result.scalar_one_or_none() is not None

        if not team_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        return {"logs": deployment.logs or "", "status": deployment.status}

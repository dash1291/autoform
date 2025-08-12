from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import List, Optional
import json
import logging
import os
from botocore.exceptions import ClientError, NoCredentialsError


from core.database import get_async_session
from core.security import get_current_user
from core.config import settings
from sqlmodel import select, and_
from models.project import Project as ProjectModel, ProjectStatus
from models.team import Team, TeamMember, TeamAwsConfig
from models.environment import Environment
from models.webhook import Webhook
from schemas import Project, ProjectCreate, ProjectUpdate, User as UserSchema
from services.cloudwatch_service import CloudWatchLogsService
from services.encryption_service import encryption_service
from services.github_webhook import GitHubWebhookService
from utils.aws_client import create_client

logger = logging.getLogger(__name__)

router = APIRouter()


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


async def create_cloudwatch_service(project) -> CloudWatchLogsService:
    """Create CloudWatch service with appropriate credentials"""
    project_credentials = await get_project_aws_credentials(project)

    if project_credentials:
        return CloudWatchLogsService(
            region_name=project_credentials["region"],
            aws_credentials=project_credentials,
        )
    else:
        return CloudWatchLogsService()


async def create_aws_client(environment, service: str):
    """Create AWS client using environment's specific AWS configuration"""
    if not environment or not environment.team_aws_config_id:
        raise ValueError("Environment must have a team_aws_config_id")
    
    # Get the AWS config for this specific environment
    async with get_async_session() as session:
        aws_config_result = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.id == environment.team_aws_config_id)
        )
        aws_config = aws_config_result.scalar_one_or_none()
        
        if not aws_config:
            raise ValueError(f"AWS config not found for environment {environment.id}")
        
        # Use the environment's specific region and credentials
        region = aws_config.aws_region
        if not region:
            raise ValueError(f"AWS region not set for environment {environment.id}")
        
        # Get credentials for this AWS config
        aws_credentials = None
        if aws_config.aws_access_key_id and aws_config.aws_secret_access_key:
            aws_credentials = {
                "access_key": encryption_service.decrypt(aws_config.aws_access_key_id),
                "secret_key": encryption_service.decrypt(aws_config.aws_secret_access_key),
            }
        
        return create_client(service, region, aws_credentials)




async def check_project_access(project_id: str, user_id: str) -> bool:
    """Check if user has access to project (through team membership)"""
    async with get_async_session() as session:
        # Get project with team info
        project = await session.execute(
            select(ProjectModel).where(ProjectModel.id == project_id)
        )
        project_obj = project.scalar_one_or_none()
        
        if not project_obj:
            return False
        
        # Check if user owns the team
        team = await session.get(Team, project_obj.team_id)
        if team and team.owner_id == user_id:
            return True
        
        # Check if user is team member
        team_member = await session.execute(
            select(TeamMember).where(
                and_(TeamMember.team_id == project_obj.team_id, TeamMember.user_id == user_id)
            )
        )
        return team_member.scalar_one_or_none() is not None


async def get_user_accessible_projects(user_id: str):
    """Get all projects accessible to the user (through team membership)"""
    async with get_async_session() as session:
        # Get teams where user is owner or member
        owned_teams = await session.execute(
            select(Team.id).where(Team.owner_id == user_id)
        )
        member_teams = await session.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == user_id)
        )
        
        accessible_team_ids = list(owned_teams.scalars().all()) + list(member_teams.scalars().all())
        
        if not accessible_team_ids:
            return []
        
        # Get projects from accessible teams
        projects = await session.execute(
            select(ProjectModel).where(ProjectModel.team_id.in_(accessible_team_ids))
            .order_by(ProjectModel.created_at.desc())
        )

        # Convert projects to dict format
        result = []
        for project in projects.scalars().all():
            # Get team info
            team = await session.get(Team, project.team_id)
            
            # Check webhook status
            from models.webhook import Webhook
            webhook = await session.execute(
                select(Webhook).where(Webhook.git_repo_url == project.git_repo_url)
            )
            webhook_obj = webhook.scalar_one_or_none()
            
            project_dict = {
                "id": project.id,
                "name": project.name,
                "gitRepoUrl": project.git_repo_url,
                "branch": project.branch,
                "subdirectory": project.subdirectory,
                "healthCheckPath": project.health_check_path,
                "port": project.port,
                "cpu": project.cpu,
                "memory": project.memory,
                "diskSize": project.disk_size,
                "createdAt": project.created_at,
                "updatedAt": project.updated_at,
                "teamId": project.team_id,
                "webhookConfigured": bool(webhook_obj and webhook_obj.is_active),
                "team": {
                    "id": team.id,
                    "name": team.name,
                } if team else None
            }
            result.append(project_dict)

        return result


@router.get("/", response_model=List[Project])
async def get_projects(current_user: UserSchema = Depends(get_current_user)):
    """Get all projects accessible to the current user (personal + team projects)"""
    logger.info(f"Getting projects for user: {current_user.id}")

    projects = await get_user_accessible_projects(current_user.id)

    logger.info(f"Found {len(projects)} projects accessible to user {current_user.id}")
    return projects


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate, current_user: UserSchema = Depends(get_current_user)
):
    """Create a new project"""

    # If team_id is provided, verify user has access to the team
    if project.team_id:
        async with get_async_session() as session:
            # Check if user owns the team
            team = await session.get(Team, project.team_id)
            team_access = False
            
            if team and team.owner_id == current_user.id:
                team_access = True
            else:
                # Check if user is team member
                team_member = await session.execute(
                    select(TeamMember).where(
                        and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                    )
                )
                team_access = team_member.scalar_one_or_none() is not None

            if not team_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this team",
                )

    # Check if project name already exists in team
    if not project.team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team ID is required. All projects must belong to a team.",
        )
    
    async with get_async_session() as session:
        existing_project = await session.execute(
            select(ProjectModel).where(
                and_(ProjectModel.name == project.name, ProjectModel.team_id == project.team_id)
            )
        )
        
        if existing_project.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A project with this name already exists in the team",
            )

    # Create the project
    async with get_async_session() as session:
        new_project = ProjectModel(
            name=project.name,
            git_repo_url=project.git_repo_url,
            team_id=project.team_id,
            user_id=current_user.id,
            auto_deploy_enabled=project.auto_deploy_enabled,
        )
        
        session.add(new_project)
        await session.commit()
        await session.refresh(new_project)
        
        # Get team info
        team = await session.get(Team, new_project.team_id)
        
        # Check webhook status
        webhook = await session.execute(
            select(Webhook).where(Webhook.git_repo_url == new_project.git_repo_url)
        )
        webhook_obj = webhook.scalar_one_or_none()
        
        # Convert to dict format
        project_dict = {
            "id": new_project.id,
            "name": new_project.name,
            "gitRepoUrl": new_project.git_repo_url,
            "branch": new_project.branch,
            "subdirectory": new_project.subdirectory,
            "healthCheckPath": new_project.health_check_path,
            "port": new_project.port,
            "cpu": new_project.cpu,
            "memory": new_project.memory,
            "diskSize": new_project.disk_size,
            "createdAt": new_project.created_at,
            "updatedAt": new_project.updated_at,
            "teamId": new_project.team_id,
            "autoDeployEnabled": new_project.auto_deploy_enabled,
            "webhookConfigured": bool(webhook_obj and webhook_obj.is_active),
            "team": {
                "id": team.id,
                "name": team.name,
            } if team else None
        }
        
        logger.info(f"Project '{project.name}' created successfully for team {project.team_id}")
        return project_dict


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, current_user: UserSchema = Depends(get_current_user)):
    """Get a specific project"""
    # Check if user has access to this project
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team info
        team = await session.get(Team, project.team_id)
        
        # Check webhook status
        webhook = await session.execute(
            select(Webhook).where(Webhook.git_repo_url == project.git_repo_url)
        )
        webhook_obj = webhook.scalar_one_or_none()
        
        # Convert to dict format
        project_dict = {
            "id": project.id,
            "name": project.name,
            "gitRepoUrl": project.git_repo_url,
            "branch": project.branch,
            "subdirectory": project.subdirectory,
            "healthCheckPath": project.health_check_path,
            "port": project.port,
            "cpu": project.cpu,
            "memory": project.memory,
            "diskSize": project.disk_size,
            "createdAt": project.created_at,
            "updatedAt": project.updated_at,
            "teamId": project.team_id,
            "autoDeployEnabled": project.auto_deploy_enabled,
            "webhookConfigured": bool(webhook_obj and webhook_obj.is_active),
            "team": {
                "id": team.id,
                "name": team.name,
            } if team else None
        }
        
        return project_dict


@router.put("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    current_user: UserSchema = Depends(get_current_user),
):
    """Update a project"""
    # Check if user has access to this project
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        logger.info(f"Updating project {project_id} with data: {project_update}")
        
        # Repository configuration
        if project_update.git_repo_url is not None:
            project.git_repo_url = project_update.git_repo_url
        if project_update.auto_deploy_enabled is not None:
            project.auto_deploy_enabled = project_update.auto_deploy_enabled
        
        # Project-level settings that apply to all environments
        if hasattr(project_update, 'subdirectory') and project_update.subdirectory is not None:
            project.subdirectory = project_update.subdirectory
        if hasattr(project_update, 'port') and project_update.port is not None:
            project.port = project_update.port
        if hasattr(project_update, 'health_check_path') and project_update.health_check_path is not None:
            project.health_check_path = project_update.health_check_path
        
        session.add(project)
        await session.commit()
        await session.refresh(project)
        
        # Convert to dict format for return
        project_dict = {
            "id": project.id,
            "name": project.name,
            "gitRepoUrl": project.git_repo_url,
            "branch": project.branch,
            "subdirectory": project.subdirectory,
            "healthCheckPath": project.health_check_path,
            "port": project.port,
            "cpu": project.cpu,
            "memory": project.memory,
            "diskSize": project.disk_size,
            "createdAt": project.created_at,
            "updatedAt": project.updated_at,
            "teamId": project.team_id,
            "autoDeployEnabled": project.auto_deploy_enabled,
        }
        
        logger.info(f"Project {project_id} updated successfully")
        return project_dict


@router.delete("/{project_id}")
async def delete_project(
    project_id: str, 
    delete_infrastructure: bool = True,
    current_user: UserSchema = Depends(get_current_user)
):
    """Delete a project and optionally its infrastructure"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        deletion_summary = {"infrastructure_deleted": False, "resources": {}}
        
        # Delete AWS infrastructure if requested
        if delete_infrastructure:
            try:
                from services.project_deletion import delete_project_infrastructure
                
                # Get AWS credentials for the project
                project_credentials = await get_project_aws_credentials(project)
                region = project_credentials["region"] if project_credentials else os.getenv("AWS_REGION", "us-east-1")
                
                # Delete infrastructure
                logger.info(f"Deleting infrastructure for project {project_id}")
                deletion_result = await delete_project_infrastructure(
                    project_id=project_id,
                    region=region,
                    aws_credentials=project_credentials
                )
                
                deletion_summary["infrastructure_deleted"] = deletion_result["success"]
                deletion_summary["resources"] = {
                    "deleted": deletion_result["deleted_resources"],
                    "failed": deletion_result["failed_resources"],
                    "errors": deletion_result["errors"]
                }
                
                if not deletion_result["success"] and deletion_result["failed_resources"]:
                    logger.warning(f"Some resources failed to delete for project {project_id}: {deletion_result['failed_resources']}")
                    
            except Exception as e:
                logger.error(f"Error deleting infrastructure for project {project_id}: {e}")
                deletion_summary["infrastructure_deleted"] = False
                deletion_summary["resources"]["errors"] = [str(e)]
        
        # Delete all related records first to avoid foreign key constraints
        # Delete environment variables
        from models.environment import EnvironmentVariable as EnvVarModel
        env_vars = await session.execute(
            select(EnvVarModel).where(EnvVarModel.project_id == project_id)
        )
        for env_var in env_vars.scalars().all():
            await session.delete(env_var)
        
        # Delete deployments
        from models.deployment import Deployment
        deployments = await session.execute(
            select(Deployment).where(Deployment.project_id == project_id)
        )
        for deployment in deployments.scalars().all():
            await session.delete(deployment)
        
        # Delete environments
        environments = await session.execute(
            select(Environment).where(Environment.project_id == project_id)
        )
        for environment in environments.scalars().all():
            await session.delete(environment)
        
        # Delete webhooks (if they match the project's git repo URL)
        if project.git_repo_url:
            from models.webhook import Webhook
            webhooks = await session.execute(
                select(Webhook).where(Webhook.git_repo_url == project.git_repo_url)
            )
            for webhook in webhooks.scalars().all():
                await session.delete(webhook)
        
        # Finally, delete the project
        await session.delete(project)
        await session.commit()

    return {
        "message": "Project deleted successfully",
        "infrastructure_deletion": deletion_summary
    }


@router.get("/{project_id}/service-status")
async def get_service_status(
    project_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Get the actual ECS service status and health"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Check if any environment in the project has been deployed
        deployed_environment = await session.execute(
            select(Environment).where(
                and_(
                    Environment.project_id == project_id,
                    Environment.ecs_service_arn.isnot(None)
                )
            )
        )
        deployed_env = deployed_environment.scalar_one_or_none()
    
    if not deployed_env:
        return {
            "status": "NOT_DEPLOYED",
            "message": "Service not deployed",
            "healthy": False,
        }

    import os
    from botocore.exceptions import ClientError

    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        ecs_client = await create_aws_client(deployed_env, "ecs")

        # Get cluster and service identifiers from the deployed environment
        cluster_identifier = deployed_env.ecs_cluster_arn or "default"
        if cluster_identifier.startswith("arn:aws:ecs:"):
            cluster_identifier = cluster_identifier.split("/")[-1]

        # Extract service name from ARN if it's an ARN, otherwise use as-is
        service_identifier = deployed_env.ecs_service_arn
        if service_identifier and service_identifier.startswith("arn:aws:ecs:"):
            service_identifier = service_identifier.split("/")[
                -1
            ]  # Extract service name from ARN

        # Describe the service
        service_response = ecs_client.describe_services(
            cluster=cluster_identifier, services=[service_identifier]
        )

        if not service_response["services"]:
            return {
                "status": "SERVICE_NOT_FOUND",
                "message": "ECS service not found",
                "healthy": False,
            }

        service = service_response["services"][0]

        # Get service status
        service_status = service["status"]
        running_count = service.get("runningCount", 0)
        desired_count = service.get("desiredCount", 0)
        pending_count = service.get("pendingCount", 0)

        # Get deployments info
        deployments = service.get("deployments", [])
        active_deployment = None
        for deployment in deployments:
            if deployment["status"] == "PRIMARY":
                active_deployment = deployment
                break

        # Check for recent events (last 10)
        events = service.get("events", [])[:10]
        recent_events = []
        for event in events:
            recent_events.append(
                {
                    "message": event.get("message", ""),
                    "createdAt": event.get("createdAt").isoformat()
                    if event.get("createdAt")
                    else None,
                }
            )

        # Determine health status
        healthy = (
            service_status == "ACTIVE"
            and running_count == desired_count
            and running_count > 0
            and pending_count == 0
        )

        # Check for deployment issues
        deployment_status = "STABLE"
        deployment_in_progress = False

        if active_deployment:
            rollout_state = active_deployment.get("rolloutState", "")
            deployment_running_count = active_deployment.get("runningCount", 0)
            deployment_desired_count = active_deployment.get("desiredCount", 0)

            # Check if deployment is actually complete
            if rollout_state == "IN_PROGRESS":
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif deployment_running_count < deployment_desired_count:
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif rollout_state == "COMPLETED":
                deployment_status = "STABLE"
            else:
                # If rollout state is not explicitly COMPLETED, consider it in progress
                if rollout_state in ["PENDING", "IN_PROGRESS"]:
                    deployment_status = "IN_PROGRESS"
                    deployment_in_progress = True

        # Check for crash loops and failure reasons by examining events
        crash_loop_detected = False
        failure_reasons = []

        if events:
            # Look for repeated task stopped messages
            stopped_events = [
                e for e in events[:5] if "has stopped" in e.get("message", "")
            ]
            if len(stopped_events) >= 3:
                crash_loop_detected = True

            # Only extract failure reasons if service is not healthy
            if not healthy or deployment_in_progress:
                # Extract failure reasons from recent events
                for event in events[:10]:  # Check last 10 events
                    message = event.get("message", "").lower()

                    # Health check failures
                    if "health check" in message and (
                        "failed" in message or "failing" in message
                    ):
                        failure_reasons.append(
                            "Health check is failing - check your health check endpoint"
                        )

                    # Task stopped due to health check
                    elif "task stopped" in message and "health check" in message:
                        failure_reasons.append(
                            "Tasks are being stopped due to failed health checks"
                        )

                    # Port binding issues
                    elif "port" in message and (
                        "bind" in message or "already in use" in message
                    ):
                        failure_reasons.append(
                            "Port binding issue - check if the port is already in use"
                        )

                    # Memory issues
                    elif "memory" in message and (
                        "limit" in message or "oom" in message or "killed" in message
                    ):
                        failure_reasons.append(
                            "Container running out of memory - consider increasing memory allocation"
                        )

                    # Exit code issues
                    elif "exit code" in message and "non-zero" in message:
                        failure_reasons.append(
                            "Application exiting with errors - check application logs"
                        )

                    # Image pull issues
                    elif "image" in message and (
                        "pull" in message or "not found" in message
                    ):
                        failure_reasons.append(
                            "Container image pull failed - check if image exists"
                        )

                    # Resource issues
                    elif "resource" in message and (
                        "insufficient" in message or "unavailable" in message
                    ):
                        failure_reasons.append(
                            "Insufficient resources available - check CPU/memory limits"
                        )

                # Remove duplicates while preserving order
                failure_reasons = list(dict.fromkeys(failure_reasons))

        # Determine overall status
        if not healthy or deployment_in_progress:
            if crash_loop_detected:
                overall_status = "CRASH_LOOP"
            elif deployment_status != "STABLE":
                overall_status = deployment_status
            elif running_count == 0:
                overall_status = "NO_RUNNING_TASKS"
            elif running_count < desired_count:
                overall_status = "DEGRADED"
            else:
                overall_status = "UNHEALTHY"
        else:
            overall_status = "HEALTHY"

        return {
            "status": overall_status,
            "healthy": healthy,
            "service": {
                "status": service_status,
                "runningCount": running_count,
                "desiredCount": desired_count,
                "pendingCount": pending_count,
            },
            "deployment": {
                "status": deployment_status,
                "rolloutState": active_deployment.get("rolloutState")
                if active_deployment
                else None,
            },
            "crashLoopDetected": crash_loop_detected,
            "failureReasons": failure_reasons[
                :3
            ],  # Show up to 3 most recent failure reasons
            "recentEvents": recent_events[:5],  # Only return last 5 events
            "message": _get_status_message(
                overall_status, running_count, desired_count
            ),
        }

    except ClientError as e:
        logger.error(f"Error checking service status: {e}")
        return {
            "status": "ERROR",
            "message": f"Error checking service status: {e.response['Error']['Message']}",
            "healthy": False,
        }
    except Exception as e:
        logger.error(f"Unexpected error checking service status: {e}")
        return {
            "status": "ERROR",
            "message": f"Unexpected error: {str(e)}",
            "healthy": False,
        }


def _get_status_message(status: str, running: int, desired: int) -> str:
    """Get a human-readable status message"""
    messages = {
        "HEALTHY": "Service is running normally",
        "CRASH_LOOP": "Container is repeatedly crashing. Check logs for errors.",
        "NO_RUNNING_TASKS": "No containers are running",
        "DEGRADED": f"Only {running} of {desired} containers are running",
        "IN_PROGRESS": "Service is being deployed",
        "UNHEALTHY": "Service is unhealthy",
        "NOT_DEPLOYED": "Service not deployed",
        "SERVICE_NOT_FOUND": "ECS service not found",
        "ERROR": "Error checking service status",
    }
    return messages.get(status, status)


@router.get("/{project_id}/exec")
async def check_exec_availability(
    project_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Check if shell execution is available for the project"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Check if any environment in the project has been deployed
        deployed_environment = await session.execute(
            select(Environment).where(
                and_(
                    Environment.project_id == project_id,
                    Environment.ecs_service_arn.isnot(None)
                )
            )
        )
        deployed_env = deployed_environment.scalar_one_or_none()
    
    if not deployed_env:
        return {
            "available": False,
            "status": "not_deployed",
            "reason": "Project must be deployed to access shell",
        }

    # Check if there are running tasks
    from botocore.exceptions import ClientError

    try:
        ecs_client = await create_aws_client(deployed_env, "ecs")

        # Extract cluster name from ARN or use default
        cluster_name = deployed_env.ecs_cluster_arn or "default"
        if cluster_name and cluster_name.startswith("arn:aws:ecs:"):
            cluster_name = cluster_name.split("/")[-1]

        # Extract service name from ARN
        service_name = deployed_env.ecs_service_arn
        if service_name and service_name.startswith("arn:aws:ecs:"):
            service_name = service_name.split("/")[-1]

        logger.info(
            f"Checking shell access for service: {service_name} in cluster: {cluster_name}"
        )

        # List tasks for the service
        response = ecs_client.list_tasks(
            cluster=cluster_name, serviceName=service_name, desiredStatus="RUNNING"
        )

        running_tasks = response.get("taskArns", [])

        if not running_tasks:
            logger.warning(
                f"No running tasks found for service {service_name} in cluster {cluster_name}"
            )
            return {
                "available": False,
                "status": "no_tasks",
                "reason": "No running containers found",
                "taskCount": 0,
                "debug": {
                    "serviceName": service_name,
                    "clusterName": cluster_name,
                    "region": region,
                },
            }

        # Get task details to find container names
        tasks_response = ecs_client.describe_tasks(
            cluster=cluster_name, tasks=running_tasks[:1]  # Just check the first task
        )

        if tasks_response["tasks"]:
            task = tasks_response["tasks"][0]
            containers = [container["name"] for container in task.get("containers", [])]

            # Get the first container name (main container)
            container_name = containers[0] if containers else "app"

            return {
                "available": True,
                "status": "ready",
                "taskArn": task["taskArn"],
                "clusterArn": deployed_env.ecs_cluster_arn,  # Return the full cluster ARN
                "containerName": container_name,  # Added containerName
                "taskCount": len(running_tasks),
                "containers": containers,
                "region": region,  # Add region info for frontend
            }
        else:
            return {
                "available": False,
                "status": "no_tasks",
                "reason": "No running containers found",
                "taskCount": 0,
            }

    except ClientError as e:
        logger.error(f"Error checking ECS tasks: {e}")
        return {
            "available": False,
            "status": "error",
            "reason": f"Error checking container status: {e.response['Error']['Message']}",
        }
    except Exception as e:
        logger.error(f"Unexpected error checking shell availability: {e}")
        return {
            "available": False,
            "status": "error",
            "reason": f"Unexpected error: {str(e)}",
        }


@router.post("/{project_id}/exec/command")
async def execute_command(
    project_id: str, command_data: dict, current_user: UserSchema = Depends(get_current_user)
):
    """Execute a command in the project container"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Check if any environment in the project has been deployed
        deployed_environment = await session.execute(
            select(Environment).where(
                and_(
                    Environment.project_id == project_id,
                    Environment.ecs_service_arn.isnot(None)
                )
            )
        )
        deployed_env = deployed_environment.scalar_one_or_none()
    
    if not deployed_env:
        return {
            "success": False,
            "message": "Project must be deployed to execute commands",
        }

    command = command_data.get("command", "")
    if not command:
        return {"success": False, "message": "No command provided"}

    import os
    from botocore.exceptions import ClientError

    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        ecs_client = await create_aws_client(deployed_env, "ecs")

        # Extract cluster ARN or use default
        cluster_arn = deployed_env.ecs_cluster_arn or "default"

        # Get a running task
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_arn,
            serviceName=deployed_env.ecs_service_arn,
            desiredStatus="RUNNING",
        )

        running_tasks = tasks_response.get("taskArns", [])
        if not running_tasks:
            return {"success": False, "message": "No running tasks found"}

        # Execute command on the first running task
        task_arn = running_tasks[0]

        # Get task details to find container name
        task_details = ecs_client.describe_tasks(cluster=cluster_arn, tasks=[task_arn])

        if not task_details["tasks"]:
            return {"success": False, "message": "Task not found"}

        # Get the first container name (usually the main app container)
        container_name = None
        for container in task_details["tasks"][0].get("containers", []):
            if container.get("name"):
                container_name = container["name"]
                break

        if not container_name:
            return {"success": False, "message": "No container found in task"}

        # Execute command using ECS Exec
        exec_response = ecs_client.execute_command(
            cluster=cluster_arn,
            task=task_arn,
            container=container_name,
            command=command,
            interactive=True,
        )

        return {
            "success": True,
            "sessionId": exec_response.get("session", {}).get("sessionId"),
            "streamUrl": exec_response.get("session", {}).get("streamUrl"),
            "tokenValue": exec_response.get("session", {}).get("tokenValue"),
            "taskArn": task_arn,
            "container": container_name,
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if (
            error_code == "InvalidParameterException"
            and "execute command" in error_message
        ):
            return {
                "success": False,
                "message": "ECS Exec is not enabled for this service. Shell access requires ECS Exec to be enabled during deployment.",
            }

        logger.error(f"Error executing command: {e}")
        return {
            "success": False,
            "message": f"Error executing command: {error_message}",
        }
    except Exception as e:
        logger.error(f"Unexpected error executing command: {e}")
        return {"success": False, "message": f"Unexpected error: {str(e)}"}


@router.get("/{project_id}/logs")
async def get_project_logs(
    project_id: str,
    limit: int = 100,
    hours_back: int = 1,
    current_user: UserSchema = Depends(get_current_user),
):
    """Get application logs for a project from CloudWatch"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Check if any environment in the project has been deployed (has ECS service)
        deployed_environments = await session.execute(
            select(Environment).where(
                and_(
                    Environment.project_id == project_id,
                    Environment.ecs_service_arn.isnot(None)
                )
            )
        )
        deployed_envs = deployed_environments.scalars().all()
    
    if not deployed_envs:
        return {
            "logs": [],
            "message": "Project must be deployed to view application logs",
            "logGroupName": f"/ecs/{project.name}",
            "totalStreams": 0,
        }

    # Fetch logs from CloudWatch
    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        logs_data = await cloudwatch_svc.get_project_logs(
            project_name=project.name, limit=limit, hours_back=hours_back
        )
        return logs_data
    except Exception as e:
        logger.error(f"Error fetching logs for project {project_id}: {str(e)}")
        return {
            "logs": [],
            "message": f"Error fetching logs: {str(e)}",
            "logGroupName": f"/ecs/{project.name}",
            "totalStreams": 0,
        }


@router.get("/{project_id}/deployed-resources")
async def get_project_deployed_resources(
    project_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Get information about deployed AWS resources for a project"""
    # Check if project exists and belongs to user or user is team member
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

    try:
        # Get deployed environment first to get the correct region
        deployed_environment = await session.execute(
            select(Environment).where(
                and_(
                    Environment.project_id == project_id,
                    Environment.ecs_service_arn.isnot(None)
                )
            )
        )
        deployed_env = deployed_environment.scalar_one_or_none()
        
        # Get region from the deployed environment's AWS config
        if not deployed_env:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="No deployed environment found for this project"
            )
        
        if not deployed_env.team_aws_config_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deployed environment has no AWS configuration"
            )
        
        # Get the TeamAwsConfig to find the correct region
        aws_config_result = await session.execute(
            select(TeamAwsConfig).where(TeamAwsConfig.id == deployed_env.team_aws_config_id)
        )
        aws_config = aws_config_result.scalar_one_or_none()
        
        if not aws_config or not aws_config.aws_region:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS configuration missing or has no region configured"
            )
        
        region = aws_config.aws_region
        logger.info(f"Using region {region} from deployed environment's AWS config")

        logger.info(
            f"Getting deployed resources for project {project_id} in region {region}"
        )

        # Initialize AWS clients
        ecs_client = await create_aws_client(deployed_env, "ecs")
        ec2_client = await create_aws_client(deployed_env, "ec2")
        elbv2_client = await create_aws_client(deployed_env, "elbv2")

        result = {
            "vpc": None,
            "subnets": [],
            "cluster": None,
            "service": None,
            "loadBalancer": None,
        }

        # If deployed environment has stored network configuration, use that
        if deployed_env and deployed_env.existing_vpc_id:
            try:
                vpc_response = ec2_client.describe_vpcs(VpcIds=[deployed_env.existing_vpc_id])
                if vpc_response["Vpcs"]:
                    vpc = vpc_response["Vpcs"][0]
                    vpc_name = deployed_env.existing_vpc_id
                    for tag in vpc.get("Tags", []):
                        if tag["Key"] == "Name":
                            vpc_name = tag["Value"]
                            break

                    result["vpc"] = {
                        "id": vpc["VpcId"],
                        "name": vpc_name,
                        "cidrBlock": vpc["CidrBlock"],
                    }
            except ClientError:
                pass

        if deployed_env and deployed_env.existing_subnet_ids:
            try:
                import json

                subnet_ids = json.loads(deployed_env.existing_subnet_ids)
                if subnet_ids:
                    subnets_response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
                    subnets = []
                    for subnet in subnets_response["Subnets"]:
                        subnet_name = subnet["SubnetId"]
                        for tag in subnet.get("Tags", []):
                            if tag["Key"] == "Name":
                                subnet_name = tag["Value"]
                                break

                        subnets.append(
                            {
                                "id": subnet["SubnetId"],
                                "name": subnet_name,
                                "cidrBlock": subnet["CidrBlock"],
                                "availabilityZone": subnet["AvailabilityZone"],
                            }
                        )
                    result["subnets"] = subnets
            except (ClientError, json.JSONDecodeError):
                pass

        if deployed_env and deployed_env.existing_cluster_arn:
            try:
                cluster_response = ecs_client.describe_clusters(
                    clusters=[deployed_env.existing_cluster_arn]
                )
                if cluster_response["clusters"]:
                    cluster = cluster_response["clusters"][0]
                    result["cluster"] = {
                        "arn": cluster["clusterArn"],
                        "name": cluster["clusterName"],
                        "runningTasksCount": cluster["runningTasksCount"],
                        "activeServicesCount": cluster["activeServicesCount"],
                    }
            except ClientError:
                pass
        
        if deployed_env and deployed_env.ecs_service_arn:
            try:
                # Extract service name from ARN if it's an ARN
                service_identifier = deployed_env.ecs_service_arn
                if service_identifier.startswith("arn:aws:ecs:"):
                    service_identifier = service_identifier.split("/")[-1]

                # Extract cluster name from ARN if it's an ARN
                cluster_identifier = deployed_env.ecs_cluster_arn or "default"
                if cluster_identifier.startswith("arn:aws:ecs:"):
                    cluster_identifier = cluster_identifier.split("/")[-1]

                service_response = ecs_client.describe_services(
                    cluster=cluster_identifier, services=[service_identifier]
                )
                if service_response["services"]:
                    service = service_response["services"][0]
                    result["service"] = {
                        "arn": service["serviceArn"],
                        "name": service["serviceName"],
                        "status": service["status"],
                        "runningCount": service["runningCount"],
                        "desiredCount": service["desiredCount"],
                    }

                    # Get cluster information if not already set from existing resources
                    if not result["cluster"]:
                        cluster_response = ecs_client.describe_clusters(
                            clusters=[cluster_identifier]
                        )
                        if cluster_response["clusters"]:
                            cluster = cluster_response["clusters"][0]
                            result["cluster"] = {
                                "arn": cluster["clusterArn"],
                                "name": cluster["clusterName"],
                                "status": cluster["status"],
                                "runningTasksCount": cluster["runningTasksCount"],
                                "activeServicesCount": cluster["activeServicesCount"],
                            }

                    # Extract network configuration from Fargate service if not already set
                    if not result["vpc"] or not result["subnets"]:
                        network_config = service.get("networkConfiguration", {}).get(
                            "awsvpcConfiguration", {}
                        )
                        if network_config:
                            subnet_ids = network_config.get("subnets", [])
                            if subnet_ids:
                                # Get VPC and subnet info from service network configuration
                                subnet_response = ec2_client.describe_subnets(
                                    SubnetIds=subnet_ids
                                )
                                if subnet_response["Subnets"]:
                                    # Set VPC info if not already set
                                    if not result["vpc"]:
                                        vpc_id = subnet_response["Subnets"][0]["VpcId"]
                                        vpc_response = ec2_client.describe_vpcs(
                                            VpcIds=[vpc_id]
                                        )
                                        if vpc_response["Vpcs"]:
                                            vpc = vpc_response["Vpcs"][0]
                                            vpc_name = vpc_id
                                            for tag in vpc.get("Tags", []):
                                                if tag["Key"] == "Name":
                                                    vpc_name = tag["Value"]
                                                    break

                                            result["vpc"] = {
                                                "id": vpc["VpcId"],
                                                "name": vpc_name,
                                                "cidrBlock": vpc["CidrBlock"],
                                            }

                                    # Set subnet info if not already set
                                    if not result["subnets"]:
                                        subnets = []
                                        for subnet in subnet_response["Subnets"]:
                                            subnet_name = subnet["SubnetId"]
                                            for tag in subnet.get("Tags", []):
                                                if tag["Key"] == "Name":
                                                    subnet_name = tag["Value"]
                                                    break

                                            subnets.append(
                                                {
                                                    "id": subnet["SubnetId"],
                                                    "name": subnet_name,
                                                    "cidrBlock": subnet["CidrBlock"],
                                                    "availabilityZone": subnet[
                                                        "AvailabilityZone"
                                                    ],
                                                }
                                            )

                                        result["subnets"] = subnets

            except ClientError as e:
                logger.error(f"Error getting deployed resources: {e}")
                pass

        # Try to find load balancer from deployed environments
        if deployed_env and deployed_env.alb_arn:
            try:
                lb_response = elbv2_client.describe_load_balancers(
                    LoadBalancerArns=[deployed_env.alb_arn]
                )
                if lb_response["LoadBalancers"]:
                    lb = lb_response["LoadBalancers"][0]
                    result["loadBalancer"] = {
                        "arn": lb["LoadBalancerArn"],
                        "name": lb["LoadBalancerName"],
                        "dnsName": lb["DNSName"],
                        "scheme": lb["Scheme"],
                        "state": lb["State"]["Code"],
                    }
            except ClientError:
                pass

        return result

    except NoCredentialsError:
        return {
            "vpc": None,
            "subnets": [],
            "cluster": None,
            "service": None,
            "loadBalancer": None,
            "error": "AWS credentials not configured",
        }
    except Exception as e:
        logger.error(f"Error fetching deployed resources: {str(e)}")
        return {
            "vpc": None,
            "subnets": [],
            "cluster": None,
            "service": None,
            "loadBalancer": None,
            "error": f"Error fetching deployed resources: {str(e)}",
        }


@router.get("/{project_id}/debug-logs")
async def debug_project_logs(
    project_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Debug endpoint to see what log groups and streams exist"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        log_group_info = await cloudwatch_svc.get_log_group_info(project.name)
        return {
            "project_name": project.name,
            "expected_log_group": f"/ecs/{project.name}",
            "log_group_info": log_group_info,
        }
    except Exception as e:
        return {
            "project_name": project.name,
            "expected_log_group": f"/ecs/{project.name}",
            "error": str(e),
        }


@router.post("/{project_id}/webhook/configure")
async def configure_webhook(
    project_id: str,
    github_access_token: Optional[str] = Header(None, alias="X-GitHub-Token"),
    current_user: UserSchema = Depends(get_current_user),
):
    """Configure webhook for automatic deployments"""
    # Check if project exists and user has access through team
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Find or create webhook for this repository
        webhook = await session.execute(
            select(Webhook).where(Webhook.git_repo_url == project.git_repo_url)
        )
        webhook_obj = webhook.scalar_one_or_none()

        if not webhook_obj:
            import secrets

            webhook_secret = secrets.token_urlsafe(32)

            webhook_obj = Webhook(
                git_repo_url=project.git_repo_url,
                secret=webhook_secret,
                is_active=True,
            )
            session.add(webhook_obj)
            await session.commit()
            await session.refresh(webhook_obj)

        # Associate project with webhook if not already associated
        if not project.webhook_id:
            project.webhook_id = webhook_obj.id
            session.add(project)
            await session.commit()

    # Webhook URL
    base_url = settings.webhook_base_url or settings.backend_url
    webhook_url = f"{base_url}/api/webhook/github"

    # If GitHub access token provided, try to create webhook automatically
    if github_access_token:
        try:
            webhook_service = GitHubWebhookService()
            webhook_result = await webhook_service.create_webhook(
                git_repo_url=project.git_repo_url,
                webhook_url=webhook_url,
                webhook_secret=webhook_obj.secret,
                access_token=github_access_token,
            )

            # Webhook configured successfully (status determined by relationship)

            return {
                "webhookUrl": webhook_url,
                "webhookSecret": webhook_obj.secret,
                "automatic": True,
                "webhookId": webhook_result.get("id"),
                "status": "created"
                if webhook_result.get("created")
                else "updated"
                if webhook_result.get("updated")
                else "exists",
            }
        except Exception as e:
            logger.error(f"Failed to automatically create webhook: {str(e)}")
            # Fall back to manual instructions

    # Return manual instructions
    return {
        "webhookUrl": webhook_url,
        "webhookSecret": webhook_obj.secret,
        "automatic": False,
        "instructions": {
            "1": "Go to your GitHub repository settings",
            "2": "Click on 'Webhooks' in the left sidebar",
            "3": "Click 'Add webhook'",
            "4": f"Set Payload URL to: {webhook_url}",
            "5": "Set Content type to: application/json",
            "6": f"Set Secret to: {webhook_obj.secret}",
            "7": "Select 'Just the push event'",
            "8": "Make sure 'Active' is checked",
            "9": "Click 'Add webhook'",
        },
    }


@router.delete("/{project_id}/webhook")
async def delete_webhook_config(
    project_id: str,
    github_access_token: Optional[str] = Header(None, alias="X-GitHub-Token"),
    current_user: UserSchema = Depends(get_current_user),
):
    """Delete webhook configuration"""
    # Check if project exists and belongs to user
    async with get_async_session() as session:
        project = await session.get(ProjectModel, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Check team access
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        has_access = team.owner_id == current_user.id
        if not has_access:
            member = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get webhook
        webhook_result = await session.execute(
            select(Webhook).where(Webhook.git_repo_url == project.git_repo_url)
        )
        webhook = webhook_result.scalar_one_or_none()

        # If GitHub access token provided, try to delete webhook from GitHub
        if github_access_token and webhook:
            try:
                base_url = settings.webhook_base_url or settings.backend_url
                webhook_url = f"{base_url}/api/webhook/github"
                webhook_service = GitHubWebhookService()
                await webhook_service.delete_webhook(
                    git_repo_url=project.git_repo_url,
                    webhook_url=webhook_url,
                    access_token=github_access_token,
                )
            except Exception as e:
                logger.error(f"Failed to delete webhook from GitHub: {str(e)}")
                # Continue with local deletion even if GitHub deletion fails

        # Dissociate project from webhook and disable auto-deploy
        project.webhook_id = None
        project.auto_deploy_enabled = False
        session.add(project)
        await session.commit()

        # Check if any other projects are using this webhook
        if webhook:
            other_projects = await session.execute(
                select(ProjectModel).where(
                    and_(ProjectModel.webhook_id == webhook.id, ProjectModel.id != project_id)
                )
            )
            other_projects_list = other_projects.scalars().all()

            # If no other projects are using this webhook, delete it
            if not other_projects_list:
                await session.delete(webhook)
                await session.commit()
                logger.info(f"Deleted unused webhook for repository {project.git_repo_url}")

    return {"message": "Webhook configuration deleted successfully"}


@router.get("/{project_id}/codebuild-logs")
async def get_project_codebuild_logs(
    project_id: str, limit: int = 100, current_user: UserSchema = Depends(get_current_user)
):
    """Get CodeBuild logs for a project"""
    # Check if project exists and user has access through team
    async with get_async_session() as session:
        if not await check_project_access(project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")
        
        project = await session.get(ProjectModel, project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    # Fetch CodeBuild logs
    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        logs_data = await cloudwatch_svc.get_codebuild_logs(
            project_name=project.name, limit=limit
        )
        return logs_data
    except Exception as e:
        logger.error(
            f"Error fetching CodeBuild logs for project {project_id}: {str(e)}"
        )
        return {
            "logs": [],
            "message": f"Error fetching CodeBuild logs: {str(e)}",
            "logGroupName": None,
            "totalStreams": 0,
        }


@router.get("/environments/{environment_id}/logs")
async def get_environment_logs(
    environment_id: str,
    limit: int = 100,
    hours_back: int = 1,
    current_user: UserSchema = Depends(get_current_user),
):
    """Get application logs for an environment from CloudWatch"""
    # Check if environment exists and user has access through team
    async with get_async_session() as session:
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(status_code=404, detail="Environment not found")
        
        if not await check_project_access(environment.project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Environment not found")
        
        project = await session.get(ProjectModel, environment.project_id)

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Check if environment has been deployed
    if not environment.ecs_service_arn:
        return {
            "logs": [],
            "message": "Environment must be deployed to view application logs",
            "logGroupName": f"/ecs/{project.name}-{environment.name}",
            "totalStreams": 0,
        }

    # Fetch logs from CloudWatch
    try:
        cloudwatch_svc = await create_cloudwatch_service_for_environment(environment)
        logs_data = await cloudwatch_svc.get_environment_logs(
            project_name=project.name, 
            environment_name=environment.name,
            limit=limit, 
            hours_back=hours_back
        )
        return logs_data
    except Exception as e:
        logger.error(f"Error fetching logs for environment {environment_id}: {str(e)}")
        return {
            "logs": [],
            "message": f"Error fetching logs: {str(e)}",
            "logGroupName": f"/ecs/{project.name}-{environment.name}",
            "totalStreams": 0,
        }


@router.get("/environments/{environment_id}/exec")
async def check_environment_exec_availability(
    environment_id: str, current_user: UserSchema = Depends(get_current_user)
):
    """Check if shell execution is available for the environment"""
    # Check if environment exists and user has access through team
    async with get_async_session() as session:
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(status_code=404, detail="Environment not found")
        
        if not await check_project_access(environment.project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Environment not found")
        
        project = await session.get(ProjectModel, environment.project_id)

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Check if environment has been deployed
    if not environment.ecs_service_arn:
        return {
            "available": False,
            "status": "not_deployed",
            "reason": "Environment must be deployed to access shell",
        }

    try:
        ecs_client = await create_aws_client(environment, "ecs")

        # Extract cluster name from ARN or use default
        cluster_name = environment.ecs_cluster_arn or "default"
        if cluster_name and cluster_name.startswith("arn:aws:ecs:"):
            cluster_name = cluster_name.split("/")[-1]

        # Extract service name from ARN
        service_name = environment.ecs_service_arn
        if service_name and service_name.startswith("arn:aws:ecs:"):
            service_name = service_name.split("/")[-1]

        logger.info(
            f"Checking exec availability for environment {environment_id}: cluster={cluster_name}, service={service_name}"
        )

        # List running tasks for the service
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name, serviceName=service_name, desiredStatus="RUNNING"
        )

        running_tasks = tasks_response.get("taskArns", [])
        if not running_tasks:
            return {
                "available": False,
                "status": "no_running_tasks",
                "reason": "No running containers found",
            }

        # Get details of the first running task
        task_details = ecs_client.describe_tasks(
            cluster=cluster_name, tasks=[running_tasks[0]]
        )

        if not task_details["tasks"]:
            return {
                "available": False,
                "status": "task_not_found",
                "reason": "Task details not found",
            }

        task = task_details["tasks"][0]
        containers = [
            container["name"] for container in task.get("containers", [])
        ]

        # Get the first container name (main container)
        container_name = containers[0] if containers else "app"

        return {
            "available": True,
            "status": "ready",
            "taskArn": task["taskArn"],
            "clusterArn": environment.ecs_cluster_arn,
            "containerName": container_name,
            "taskCount": len(running_tasks),
            "containers": containers,
            "region": region,
        }
    except Exception as e:
        logger.error(f"Error checking exec availability for environment {environment_id}: {e}")
        return {
            "available": False,
            "status": "error",
            "reason": f"Error checking availability: {str(e)}",
        }


@router.post("/environments/{environment_id}/exec/command")
async def execute_environment_command(
    environment_id: str, command_data: dict, current_user: UserSchema = Depends(get_current_user)
):
    """Execute a command in the environment container"""
    # Check if environment exists and user has access through team
    async with get_async_session() as session:
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(status_code=404, detail="Environment not found")
        
        if not await check_project_access(environment.project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Environment not found")
        
        project = await session.get(ProjectModel, environment.project_id)

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Check if environment has been deployed
    if not environment.ecs_service_arn:
        return {
            "success": False,
            "message": "Environment must be deployed to execute commands",
        }

    command = command_data.get("command", "")
    if not command:
        return {"success": False, "message": "No command provided"}

    import os
    from botocore.exceptions import ClientError

    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        ecs_client = await create_aws_client(deployed_env, "ecs")

        # Extract cluster ARN or use default
        cluster_arn = environment.ecs_cluster_arn or "default"

        # Get a running task
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_arn,
            serviceName=environment.ecs_service_arn,
            desiredStatus="RUNNING",
        )

        running_tasks = tasks_response.get("taskArns", [])
        if not running_tasks:
            return {"success": False, "message": "No running tasks found"}

        # Execute command on the first running task
        task_arn = running_tasks[0]

        # Get task details to find container name
        task_details = ecs_client.describe_tasks(cluster=cluster_arn, tasks=[task_arn])

        if not task_details["tasks"]:
            return {"success": False, "message": "Task details not found"}

        task = task_details["tasks"][0]
        containers = task.get("containers", [])
        if not containers:
            return {"success": False, "message": "No containers found in task"}

        container_name = containers[0]["name"]

        # Execute the command
        response = ecs_client.execute_command(
            cluster=cluster_arn,
            task=task_arn,
            container=container_name,
            command=command,
            interactive=False,
        )

        return {
            "success": True,
            "message": "Command executed successfully",
            "taskArn": response.get("taskArn"),
            "clusterArn": response.get("clusterArn"),
            "containerName": container_name,
            "session": response.get("session", {}),
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "InvalidParameterException":
            if "enable logging" in error_message.lower():
                return {
                    "success": False,
                    "message": "ECS Exec is not enabled for this service. Shell access requires ECS Exec to be enabled during deployment.",
                }

        logger.error(f"Error executing command: {e}")
        return {
            "success": False,
            "message": f"Error executing command: {error_message}",
        }
    except Exception as e:
        logger.error(f"Unexpected error executing command: {e}")
        return {"success": False, "message": f"Unexpected error: {str(e)}"}


async def create_cloudwatch_service_for_environment(environment):
    """Create CloudWatch service with environment's team credentials"""
    # Get team AWS credentials for the environment
    async with get_async_session() as session:
        team_aws_config_result = await session.execute(
            select(TeamAwsConfig).where(
                and_(TeamAwsConfig.id == environment.team_aws_config_id, TeamAwsConfig.is_active == True)
            )
        )
        team_aws_config = team_aws_config_result.scalar_one_or_none()

    aws_credentials = None
    region = "us-east-1"
    
    if team_aws_config:
        # Decrypt team credentials
        access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
        secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)

        if access_key and secret_key:
            aws_credentials = {
                "access_key": access_key,
                "secret_key": secret_key,
            }
            region = team_aws_config.aws_region

    from services.cloudwatch_service import CloudWatchLogsService
    return CloudWatchLogsService(region_name=region, aws_credentials=aws_credentials)

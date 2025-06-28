from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import User, ProjectStatus, TeamMemberRole, EnvironmentStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/environments")
async def get_project_environments(
    project_id: str, current_user: User = Depends(get_current_user)
):
    """Get all environments for a project"""

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

    # Get all environments for this project
    environments = await prisma.environment.find_many(
        where={"projectId": project_id},
        include={
            "teamAwsConfig": True,
            "deployments": True,
            "project": True,
        },
        order={"createdAt": "asc"},
    )

    environments_response = []
    for env in environments:
        # Get AWS config info (masked)
        aws_config_info = {
            "type": "team",
            "id": env.teamAwsConfig.id,
            "name": env.teamAwsConfig.name,
            "region": env.teamAwsConfig.awsRegion,
        }

        # Find the latest deployment by sorting by createdAt
        latest_deployment = None
        if env.deployments:
            latest_deployment = max(env.deployments, key=lambda d: d.createdAt)

        environments_response.append(
            {
                "id": env.id,
                "name": env.name,
                "branch": env.branch,
                "status": env.status,
                "domain": env.domain,
                "existingVpcId": env.existingVpcId,
                "existingSubnetIds": env.existingSubnetIds,
                "existingClusterArn": env.existingClusterArn,
                "cpu": env.cpu,
                "memory": env.memory,
                "diskSize": env.diskSize,
                "subdirectory": env.project.subdirectory,
                "port": env.project.port,
                "healthCheckPath": env.project.healthCheckPath,
                "awsConfig": aws_config_info,
                "latestDeployment": {
                    "id": latest_deployment.id,
                    "status": latest_deployment.status,
                    "createdAt": latest_deployment.createdAt,
                }
                if latest_deployment
                else None,
                "createdAt": env.createdAt,
                "updatedAt": env.updatedAt,
            }
        )

    return environments_response


@router.post("/projects/{project_id}/environments")
async def create_environment(
    project_id: str,
    environment_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Create a new environment for a project"""

    # Verify project access (all projects belong to teams)
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "team": {
                "OR": [
                    {"ownerId": current_user.id},  # User owns the team
                    {
                        "members": {
                            "some": {
                                "userId": current_user.id,
                                "role": {"in": [TeamMemberRole.ADMIN]},
                            }
                        }
                    },  # User is team admin
                ]
            },
        },
        include={"team": True},
    )

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or insufficient permissions",
        )

    # Validate required fields
    name = environment_data.get("name", "").strip()
    aws_config_id = environment_data.get("awsConfigId", "").strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Environment name is required",
        )

    if not aws_config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AWS configuration is required",
        )

    # Check if environment name already exists for this project
    existing_env = await prisma.environment.find_first(
        where={"projectId": project_id, "name": name}
    )

    if existing_env:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Environment with name '{name}' already exists for this project",
        )

    # Verify team AWS config exists and user has access (all projects are team projects now)
    team_aws_config = await prisma.teamawsconfig.find_first(
        where={"id": aws_config_id, "teamId": project.teamId}
    )

    if not team_aws_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team AWS configuration not found",
        )

    # Prepare environment data
    env_data = {
        "projectId": project_id,
        "name": name,
        "teamAwsConfigId": aws_config_id,
        "branch": environment_data.get("branch", "main"),
        "cpu": environment_data.get("cpu", 256),
        "memory": environment_data.get("memory", 512),
        "diskSize": environment_data.get("diskSize", 21),
        "existingVpcId": environment_data.get("existingVpcId"),
        "existingSubnetIds": environment_data.get("existingSubnetIds"),
        "existingClusterArn": environment_data.get("existingClusterArn"),
        "status": EnvironmentStatus.CREATED,
    }

    # Create environment
    new_environment = await prisma.environment.create(
        data=env_data, include={"teamAwsConfig": True}
    )

    logger.info(
        f"Environment '{name}' created for project {project_id} by {current_user.id}"
    )

    return {
        "message": f"Environment '{name}' created successfully",
        "id": new_environment.id,
        "name": new_environment.name,
        "awsConfig": {"type": "team", "name": new_environment.teamAwsConfig.name},
    }


@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get a specific environment with full details"""

    # Get environment with all relations
    environment = await prisma.environment.find_first(
        where={"id": environment_id},
        include={
            "project": {"include": {"team": True}},
            "teamAwsConfig": True,
            "deployments": {"order_by": {"createdAt": "desc"}, "take": 10},
        },
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Verify access to the project (all projects are team projects now)
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={"teamId": project.teamId, "userId": current_user.id}
        )  # User is team member
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Prepare AWS config info
    aws_config_info = {
        "type": "team",
        "id": environment.teamAwsConfig.id,
        "name": environment.teamAwsConfig.name,
        "region": environment.teamAwsConfig.awsRegion,
    }

    return {
        "id": environment.id,
        "name": environment.name,
        "projectId": environment.projectId,
        "projectName": project.name,
        "branch": environment.branch,
        "status": environment.status,
        "ecsClusterArn": environment.ecsClusterArn,
        "ecsServiceArn": environment.ecsServiceArn,
        "albArn": environment.albArn,
        "domain": environment.domain,
        "existingVpcId": environment.existingVpcId,
        "existingSubnetIds": environment.existingSubnetIds,
        "existingClusterArn": environment.existingClusterArn,
        "cpu": environment.cpu,
        "memory": environment.memory,
        "diskSize": environment.diskSize,
        "subdirectory": environment.project.subdirectory,
        "port": environment.project.port,
        "healthCheckPath": environment.project.healthCheckPath,
        "secretsArn": environment.project.secretsArn,
        "awsConfig": aws_config_info,
        "deployments": [
            {
                "id": deployment.id,
                "status": deployment.status,
                "imageTag": deployment.imageTag,
                "commitSha": deployment.commitSha,
                "createdAt": deployment.createdAt,
            }
            for deployment in environment.deployments
        ],
        "createdAt": environment.createdAt,
        "updatedAt": environment.updatedAt,
    }


@router.put("/environments/{environment_id}")
async def update_environment(
    environment_id: str,
    environment_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update an environment"""

    # Get environment with project info
    environment = await prisma.environment.find_first(
        where={"id": environment_id}, include={"project": {"include": {"team": True}}}
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Verify access (must be team owner or team admin)
    project = environment.project
    has_admin_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={
                "teamId": project.teamId,
                "userId": current_user.id,
                "role": TeamMemberRole.ADMIN,
            }
        )  # User is team admin
    )

    if not has_admin_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin permissions required.",
        )

    # Prepare update data
    update_data = {}

    # Environment name update
    if "name" in environment_data:
        name = environment_data["name"].strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Environment name cannot be empty",
            )

        # Check if another environment with this name exists
        if name != environment.name:
            existing_env = await prisma.environment.find_first(
                where={
                    "projectId": environment.projectId,
                    "name": name,
                    "id": {"not": environment_id},
                }
            )
            if existing_env:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Environment with name '{name}' already exists for this project",
                )

        update_data["name"] = name

    # AWS config update
    if "awsConfigId" in environment_data and "awsConfigType" in environment_data:
        aws_config_id = environment_data["awsConfigId"].strip()
        aws_config_type = environment_data["awsConfigType"].strip()

        if aws_config_type == "team":
            team_aws_config = await prisma.teamawsconfig.find_first(
                where={"id": aws_config_id, "teamId": project.teamId}
            )

            if not team_aws_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Team AWS configuration not found",
                )

            update_data["teamAwsConfigId"] = aws_config_id

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid AWS config type. Only 'team' configs are supported.",
            )

    # Other configuration updates
    for field in [
        "branch",
        "cpu",
        "memory",
        "diskSize",
        "port",
        "healthCheckPath",
        "subdirectory",
        "existingVpcId",
        "existingSubnetIds",
        "existingClusterArn",
    ]:
        if field in environment_data:
            update_data[field] = environment_data[field]

    # Update environment
    updated_environment = await prisma.environment.update(
        where={"id": environment_id}, data=update_data
    )

    logger.info(f"Environment {environment_id} updated by {current_user.id}")

    return {
        "message": f"Environment '{updated_environment.name}' updated successfully",
        "id": updated_environment.id,
        "name": updated_environment.name,
    }


@router.delete("/environments/{environment_id}")
async def delete_environment(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an environment"""

    # Get environment with project info
    environment = await prisma.environment.find_first(
        where={"id": environment_id},
        include={"project": {"include": {"team": True}}, "deployments": True},
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Verify access (must be team owner or team admin)
    project = environment.project
    has_admin_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={
                "teamId": project.teamId,
                "userId": current_user.id,
                "role": TeamMemberRole.ADMIN,
            }
        )  # User is team admin
    )

    if not has_admin_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin permissions required.",
        )

    # Check if environment is currently deployed (has active AWS resources)
    if environment.status == ProjectStatus.DEPLOYED or environment.ecsServiceArn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a deployed environment. Please undeploy it first.",
        )

    # Delete environment (this will cascade delete deployments and environment variables)
    await prisma.environment.delete(where={"id": environment_id})

    logger.info(
        f"Environment {environment_id} ('{environment.name}') deleted by {current_user.id}"
    )

    return {"message": f"Environment '{environment.name}' deleted successfully"}


@router.get("/environments/{environment_id}/available-aws-configs")
async def get_available_aws_configs(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get available AWS configurations for an environment"""

    # Get environment with project info
    environment = await prisma.environment.find_first(
        where={"id": environment_id}, include={"project": {"include": {"team": True}}}
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Verify access (all projects belong to teams)
    project = environment.project
    has_access = (
        project.team.ownerId == current_user.id
        or await prisma.teammember.find_first(  # User owns team
            where={"teamId": project.teamId, "userId": current_user.id}
        )  # User is team member
    )

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    available_configs = {"teamConfigs": []}

    # Get team AWS configs (all projects belong to teams)
    team_configs = await prisma.teamawsconfig.find_many(
        where={"teamId": project.teamId, "isActive": True}
    )

    for config in team_configs:
        available_configs["teamConfigs"].append(
            {
                "id": config.id,
                "name": config.name,
                "region": config.awsRegion,
                "type": "team",
            }
        )

    return available_configs


@router.get("/{environment_id}/service-status")
async def get_environment_service_status(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get the actual ECS service status and health for a specific environment"""
    environment = await prisma.environment.find_first(
        where={
            "id": environment_id,
            "project": {
                "team": {
                    "OR": [
                        {"ownerId": current_user.id},
                        {"members": {"some": {"userId": current_user.id}}}
                    ]
                }
            }
        },
        include={
            "project": {"include": {"team": True}},
            "teamAwsConfig": True
        }
    )

    if not environment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
        )

    # Check if environment has been deployed
    if not environment.ecsServiceArn or not environment.ecsClusterArn:
        return {
            "status": "NOT_DEPLOYED",
            "message": "Environment has not been deployed yet",
            "service": None,
            "failureReasons": [],
            "crashLoopDetected": False,
        }

    try:
        # Import here to avoid circular import
        from services.deployment import DeploymentService
        from services.encryption_service import encryption_service
        
        # Get team AWS credentials for this environment
        team_aws_config = environment.teamAwsConfig
        if not team_aws_config:
            return {
                "status": "ERROR",
                "message": "No AWS credentials configured for this environment",
                "service": None,
                "failureReasons": ["No AWS credentials configured"],
                "crashLoopDetected": False,
            }

        # Decrypt credentials
        access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
        secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
        
        # Create deployment service to check status
        deployment_service = DeploymentService(
            region=team_aws_config.awsRegion, 
            aws_credentials=aws_credentials
        )

        # Get service status
        service_arn = environment.ecsServiceArn
        cluster_arn = environment.ecsClusterArn
        
        # Extract service name and cluster name from ARNs
        service_name = service_arn.split("/")[-1]
        cluster_name = cluster_arn.split("/")[-1]

        # Use the same logic as project service status
        import boto3
        from utils.aws_client import create_client

        ecs_client = create_client("ecs", team_aws_config.awsRegion, aws_credentials)

        # Get service details
        response = ecs_client.describe_services(
            cluster=cluster_name, services=[service_name]
        )

        if not response["services"]:
            return {
                "status": "NOT_FOUND",
                "message": "ECS service not found",
                "service": None,
                "failureReasons": ["ECS service not found in cluster"],
                "crashLoopDetected": False,
            }

        service = response["services"][0]
        service_status = service.get("status", "UNKNOWN")
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

            if rollout_state == "IN_PROGRESS":
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif deployment_running_count < deployment_desired_count:
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif rollout_state == "COMPLETED":
                deployment_status = "STABLE"
            else:
                if rollout_state in ["PENDING", "IN_PROGRESS"]:
                    deployment_status = "IN_PROGRESS"
                    deployment_in_progress = True

        # Check for crash loops and failure reasons
        crash_loop_detected = False
        failure_reasons = []

        if events:
            # Look for repeated task stopped messages
            stopped_events = [
                e for e in events[:5] if "has stopped" in e.get("message", "")
            ]
            if len(stopped_events) >= 3:
                crash_loop_detected = True

            # Extract failure reasons from recent events
            if not healthy or deployment_in_progress:
                for event in events[:10]:
                    message = event.get("message", "").lower()

                    if "health check" in message and ("failed" in message or "failing" in message):
                        failure_reasons.append("Health check is failing - check your health check endpoint")
                    elif "task stopped" in message and "health check" in message:
                        failure_reasons.append("Tasks are being stopped due to failed health checks")
                    elif "port" in message and ("bind" in message or "already in use" in message):
                        failure_reasons.append("Port binding issue - check if the port is already in use")
                    elif "memory" in message and ("limit" in message or "oom" in message or "killed" in message):
                        failure_reasons.append("Container running out of memory - consider increasing memory allocation")

        # Remove duplicates
        failure_reasons = list(set(failure_reasons))

        # Determine overall status
        if crash_loop_detected:
            overall_status = "CRASH_LOOP"
            status_message = f"Service is in a crash loop (running: {running_count}/{desired_count})"
        elif deployment_in_progress:
            overall_status = "IN_PROGRESS"
            status_message = f"Deployment in progress (running: {running_count}/{desired_count})"
        elif healthy:
            overall_status = "HEALTHY"
            status_message = f"Service is healthy (running: {running_count}/{desired_count})"
        elif running_count == 0:
            overall_status = "NO_RUNNING_TASKS"
            status_message = "No tasks are running"
        elif running_count < desired_count:
            overall_status = "DEGRADED"
            status_message = f"Service is degraded (running: {running_count}/{desired_count})"
        else:
            overall_status = "UNKNOWN"
            status_message = f"Service status unclear (running: {running_count}/{desired_count})"

        return {
            "status": overall_status,
            "message": status_message,
            "service": {
                "serviceName": service_name,
                "clusterName": cluster_name,
                "runningCount": running_count,
                "desiredCount": desired_count,
                "pendingCount": pending_count,
                "taskDefinition": service.get("taskDefinition", ""),
                "deploymentStatus": deployment_status,
            },
            "failureReasons": failure_reasons,
            "crashLoopDetected": crash_loop_detected,
        }

    except Exception as e:
        logger.error(f"Error getting environment service status: {e}")
        return {
            "status": "ERROR",
            "message": f"Failed to get service status: {str(e)}",
            "service": None,
            "failureReasons": [f"API Error: {str(e)}"],
            "crashLoopDetected": False,
        }

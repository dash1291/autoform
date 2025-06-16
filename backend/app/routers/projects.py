from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import List, Optional
import json
import logging
import os
from botocore.exceptions import ClientError, NoCredentialsError
    

from core.database import prisma
from core.security import get_current_user
from core.config import settings
from schemas import Project, ProjectCreate, ProjectUpdate, ProjectStatus, User
from services.cloudwatch_service import CloudWatchLogsService
from services.encryption_service import encryption_service
from services.github_webhook import GitHubWebhookService

logger = logging.getLogger(__name__)

router = APIRouter()


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


async def create_cloudwatch_service(project) -> CloudWatchLogsService:
    """Create CloudWatch service with appropriate credentials"""
    team_credentials = await get_team_aws_credentials(project)
    
    if team_credentials:
        return CloudWatchLogsService(
            region_name=team_credentials["region"],
            aws_credentials=team_credentials
        )
    else:
        return CloudWatchLogsService()


async def create_aws_client(project, service: str, region: str = None):
    """Create AWS client with team credentials if available"""
    import boto3
    import os
    
    if region is None:
        region = os.getenv('AWS_REGION', 'us-east-1')
    
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


async def check_project_access(project_id: str, user_id: str) -> bool:
    """Check if user has access to project (either owns it or is team member)"""
    project = await prisma.project.find_first(
        where={
            "id": project_id,
            "OR": [
                {"userId": user_id},  # User owns the project
                {
                    "team": {
                        "OR": [
                            {"ownerId": user_id},  # User owns the team
                            {"members": {"some": {"userId": user_id}}}  # User is team member
                        ]
                    }
                }
            ]
        }
    )
    return project is not None


async def get_user_accessible_projects(user_id: str):
    """Get all projects accessible to the user (personal + team projects)"""
    projects = await prisma.project.find_many(
        where={
            "OR": [
                {"userId": user_id},  # Personal projects
                {
                    "team": {
                        "OR": [
                            {"ownerId": user_id},  # Teams owned by user
                            {"members": {"some": {"userId": user_id}}}  # Teams user is member of
                        ]
                    }
                }
            ]
        },
        include={
            "team": True
        },
        order={"createdAt": "desc"}
    )
    
    # Convert projects to dict and handle team objects
    result = []
    for project in projects:
        project_dict = project.dict()
        if project_dict.get("team"):
            project_dict["team"] = {
                "id": project_dict["team"]["id"],
                "name": project_dict["team"]["name"]
            }
        result.append(project_dict)
    
    return result


@router.get("/", response_model=List[Project])
async def get_projects(current_user: User = Depends(get_current_user)):
    """Get all projects accessible to the current user (personal + team projects)"""
    logger.info(f"Getting projects for user: {current_user.id}")
    
    projects = await get_user_accessible_projects(current_user.id)
    
    logger.info(f"Found {len(projects)} projects accessible to user {current_user.id}")
    return projects


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new project"""
    
    # If team_id is provided, verify user has access to the team
    if project.team_id:
        team_access = await prisma.team.find_first(
            where={
                "id": project.team_id,
                "OR": [
                    {"ownerId": current_user.id},  # User owns the team
                    {"members": {"some": {"userId": current_user.id}}}  # User is team member
                ]
            }
        )
        
        if not team_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this team"
            )
    
    # Check if project name already exists in scope (personal or team)
    name_check_where = {"name": project.name}
    if project.team_id:
        name_check_where["teamId"] = project.team_id
    else:
        name_check_where["userId"] = current_user.id
        name_check_where["teamId"] = None  # Personal project
    
    existing_project = await prisma.project.find_first(where=name_check_where)
    
    if existing_project:
        scope = "team" if project.team_id else "your personal projects"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project with this name already exists in {scope}"
        )
    
    # Create the project
    project_data = {
        "name": project.name,
        "gitRepoUrl": project.git_repo_url,
        "branch": project.branch,
        "userId": current_user.id,
        "status": ProjectStatus.CREATED,
        "cpu": project.cpu,
        "memory": project.memory,
        "diskSize": project.disk_size,
        "subdirectory": project.subdirectory,
        "port": project.port,
        "healthCheckPath": project.health_check_path,
    }
    
    # Add team_id if provided
    if project.team_id:
        project_data["teamId"] = project.team_id
    
    new_project = await prisma.project.create(
        data=project_data,
        include={
            "team": True
        }
    )
    
    # Convert to dict and handle team object
    project_dict = new_project.dict()
    if project_dict.get("team"):
        project_dict["team"] = {
            "id": project_dict["team"]["id"],
            "name": project_dict["team"]["name"]
        }
    
    return project_dict


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific project"""
    # Check if user has access to this project
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    project = await prisma.project.find_unique(
        where={"id": project_id},
        include={
            "team": True
        }
    )
    
    # Convert to dict and handle team object
    project_dict = project.dict()
    if project_dict.get("team"):
        project_dict["team"] = {
            "id": project_dict["team"]["id"],
            "name": project_dict["team"]["name"]
        }
    
    return project_dict


@router.put("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a project"""
    # Check if user has access to this project
    if not await check_project_access(project_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    project = await prisma.project.find_unique(where={"id": project_id})
    
    # Prepare update data
    update_data = {}
    
    # Repository configuration
    if project_update.git_repo_url is not None:
        update_data["gitRepoUrl"] = project_update.git_repo_url
    if project_update.branch is not None:
        update_data["branch"] = project_update.branch
    if project_update.subdirectory is not None:
        update_data["subdirectory"] = project_update.subdirectory
    if project_update.port is not None:
        update_data["port"] = project_update.port
    if project_update.health_check_path is not None:
        update_data["healthCheckPath"] = project_update.health_check_path
    if project_update.auto_deploy_enabled is not None:
        update_data["autoDeployEnabled"] = project_update.auto_deploy_enabled
    
    # Network configuration
    if project_update.existing_vpc_id is not None:
        update_data["existingVpcId"] = project_update.existing_vpc_id or None
    if project_update.existing_subnet_ids is not None:
        # Convert list to JSON string
        subnet_ids_json = json.dumps(project_update.existing_subnet_ids) if project_update.existing_subnet_ids else None
        update_data["existingSubnetIds"] = subnet_ids_json
    if project_update.existing_cluster_arn is not None:
        update_data["existingClusterArn"] = project_update.existing_cluster_arn or None
    
    # Resource configuration
    if project_update.cpu is not None:
        update_data["cpu"] = project_update.cpu
    if project_update.memory is not None:
        update_data["memory"] = project_update.memory
    if project_update.disk_size is not None:
        update_data["diskSize"] = project_update.disk_size
    
    # Update project
    updated_project = await prisma.project.update(
        where={"id": project_id},
        data=update_data
    )
    
    # Track health check update status
    health_check_update_status = None
    
    # If health check path was updated, try to update the load balancer immediately
    logger.info(f"Checking health check update: health_check_path={project_update.health_check_path}, status={project.status}, albArn={project.albArn}")
    
    if (project_update.health_check_path is not None and 
        project.albArn):  # Remove the DEPLOYED requirement - allow during deployment
        
        logger.info(f"Updating health check path to {project_update.health_check_path} for project {project.name}")
        try:
            import os
            from botocore.exceptions import ClientError
            
            region = os.getenv('AWS_REGION', 'us-east-1')
            elbv2_client = await create_aws_client(project, 'elbv2', region)
            
            # Try to find target group by name first (more reliable during deployment)
            target_group_name = f"{project.name}-tg"
            target_groups_response = None
            
            try:
                # First try to find by name
                target_groups_response = elbv2_client.describe_target_groups(
                    Names=[target_group_name]
                )
                logger.info(f"Found target group by name: {target_group_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'TargetGroupNotFound':
                    logger.info(f"Target group {target_group_name} not found by name, trying by load balancer")
                    # Fallback to finding by load balancer
                    target_groups_response = elbv2_client.describe_target_groups(
                        LoadBalancerArn=project.albArn
                    )
                else:
                    raise e
            
            if not target_groups_response or not target_groups_response['TargetGroups']:
                health_check_update_status = "failed: no target groups found"
                logger.error("No target groups found for health check update")
            else:
                # Update health check path for each target group
                for target_group in target_groups_response['TargetGroups']:
                    target_group_arn = target_group['TargetGroupArn']
                
                    elbv2_client.modify_target_group(
                        TargetGroupArn=target_group_arn,
                        HealthCheckEnabled=True,
                        HealthCheckPath=project_update.health_check_path,
                        HealthCheckPort="traffic-port",
                        HealthCheckProtocol="HTTP",
                        HealthCheckTimeoutSeconds=5,
                        HealthyThresholdCount=2,
                        UnhealthyThresholdCount=2,
                        Matcher={"HttpCode": "200"}
                    )
                    
                    logger.info(f"Updated health check path to {project_update.health_check_path} for target group {target_group_arn}")
                
                health_check_update_status = "success"
        
        except ClientError as e:
            logger.error(f"Failed to update health check path in load balancer: {e}")
            health_check_update_status = f"failed: {e.response['Error']['Message']}"
        except Exception as e:
            logger.error(f"Unexpected error updating health check path: {e}")
            health_check_update_status = f"failed: {str(e)}"
    elif project_update.health_check_path is not None:
        if project.status != "DEPLOYED":
            health_check_update_status = "skipped: project not deployed"
        elif not project.albArn:
            health_check_update_status = "skipped: no load balancer found"
    
    # Add health check update status to response
    response = updated_project.dict()
    if health_check_update_status:
        response["healthCheckUpdateStatus"] = health_check_update_status
    
    return response


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a project"""
    # Check if project exists and belongs to user
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
    
    # TODO: Clean up AWS resources before deleting
    
    # Delete the project
    await prisma.project.delete(
        where={"id": project_id}
    )
    
    return {"message": "Project deleted successfully"}


@router.get("/{project_id}/service-status")
async def get_service_status(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the actual ECS service status and health"""
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
    
    # If not deployed, return appropriate status
    if not project.ecsServiceArn:
        return {
            "status": "NOT_DEPLOYED",
            "message": "Service not deployed",
            "healthy": False
        }
    
    import os
    from botocore.exceptions import ClientError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        ecs_client = await create_aws_client(project, 'ecs', region)
        
        # Get cluster and service identifiers
        cluster_identifier = project.ecsClusterArn or "default"
        service_identifier = project.ecsServiceArn
        
        # Describe the service
        service_response = ecs_client.describe_services(
            cluster=cluster_identifier,
            services=[service_identifier]
        )
        
        if not service_response['services']:
            return {
                "status": "SERVICE_NOT_FOUND",
                "message": "ECS service not found",
                "healthy": False
            }
        
        service = service_response['services'][0]
        
        # Get service status
        service_status = service['status']
        running_count = service.get('runningCount', 0)
        desired_count = service.get('desiredCount', 0)
        pending_count = service.get('pendingCount', 0)
        
        # Get deployments info
        deployments = service.get('deployments', [])
        active_deployment = None
        for deployment in deployments:
            if deployment['status'] == 'PRIMARY':
                active_deployment = deployment
                break
        
        # Check for recent events (last 10)
        events = service.get('events', [])[:10]
        recent_events = []
        for event in events:
            recent_events.append({
                "message": event.get('message', ''),
                "createdAt": event.get('createdAt').isoformat() if event.get('createdAt') else None
            })
        
        # Determine health status
        healthy = (
            service_status == 'ACTIVE' and 
            running_count == desired_count and 
            running_count > 0 and
            pending_count == 0
        )
        
        # Check for deployment issues
        deployment_status = "STABLE"
        deployment_in_progress = False
        
        if active_deployment:
            rollout_state = active_deployment.get('rolloutState', '')
            deployment_running_count = active_deployment.get('runningCount', 0)
            deployment_desired_count = active_deployment.get('desiredCount', 0)
            
            # Check if deployment is actually complete
            if rollout_state == 'IN_PROGRESS':
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif deployment_running_count < deployment_desired_count:
                deployment_status = "IN_PROGRESS"
                deployment_in_progress = True
            elif rollout_state == 'COMPLETED':
                deployment_status = "STABLE"
            else:
                # If rollout state is not explicitly COMPLETED, consider it in progress
                if rollout_state in ['PENDING', 'IN_PROGRESS']:
                    deployment_status = "IN_PROGRESS"
                    deployment_in_progress = True
        
        # Check for crash loops and failure reasons by examining events
        crash_loop_detected = False
        failure_reasons = []
        
        if events:
            # Look for repeated task stopped messages
            stopped_events = [e for e in events[:5] if 'has stopped' in e.get('message', '')]
            if len(stopped_events) >= 3:
                crash_loop_detected = True
            
            # Only extract failure reasons if service is not healthy
            if not healthy or deployment_in_progress:
                # Extract failure reasons from recent events
                for event in events[:10]:  # Check last 10 events
                    message = event.get('message', '').lower()
                    
                    # Health check failures
                    if 'health check' in message and ('failed' in message or 'failing' in message):
                        failure_reasons.append("Health check is failing - check your health check endpoint")
                    
                    # Task stopped due to health check
                    elif 'task stopped' in message and 'health check' in message:
                        failure_reasons.append("Tasks are being stopped due to failed health checks")
                    
                    # Port binding issues
                    elif 'port' in message and ('bind' in message or 'already in use' in message):
                        failure_reasons.append("Port binding issue - check if the port is already in use")
                    
                    # Memory issues
                    elif 'memory' in message and ('limit' in message or 'oom' in message or 'killed' in message):
                        failure_reasons.append("Container running out of memory - consider increasing memory allocation")
                    
                    # Exit code issues
                    elif 'exit code' in message and 'non-zero' in message:
                        failure_reasons.append("Application exiting with errors - check application logs")
                    
                    # Image pull issues
                    elif 'image' in message and ('pull' in message or 'not found' in message):
                        failure_reasons.append("Container image pull failed - check if image exists")
                    
                    # Resource issues
                    elif 'resource' in message and ('insufficient' in message or 'unavailable' in message):
                        failure_reasons.append("Insufficient resources available - check CPU/memory limits")
                
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
                "pendingCount": pending_count
            },
            "deployment": {
                "status": deployment_status,
                "rolloutState": active_deployment.get('rolloutState') if active_deployment else None
            },
            "crashLoopDetected": crash_loop_detected,
            "failureReasons": failure_reasons[:3],  # Show up to 3 most recent failure reasons
            "recentEvents": recent_events[:5],  # Only return last 5 events
            "message": _get_status_message(overall_status, running_count, desired_count)
        }
        
    except ClientError as e:
        logger.error(f"Error checking service status: {e}")
        return {
            "status": "ERROR",
            "message": f"Error checking service status: {e.response['Error']['Message']}",
            "healthy": False
        }
    except Exception as e:
        logger.error(f"Unexpected error checking service status: {e}")
        return {
            "status": "ERROR",
            "message": f"Unexpected error: {str(e)}",
            "healthy": False
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
        "ERROR": "Error checking service status"
    }
    return messages.get(status, status)


@router.get("/{project_id}/exec")
async def check_exec_availability(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Check if shell execution is available for the project"""
    # Check if project exists and belongs to user
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
    
    # Check if project has ECS service (has been deployed at least once)
    if not project.ecsServiceArn:
        return {
            "available": False,
            "status": "not_deployed",
            "reason": "Project must be deployed to access shell"
        }
    
    # Check if there are running tasks
    import os
    from botocore.exceptions import ClientError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        ecs_client = await create_aws_client(project, 'ecs', region)
        
        # Extract cluster name from ARN or use default
        cluster_name = project.ecsClusterArn or "default"
        if cluster_name and cluster_name.startswith('arn:aws:ecs:'):
            cluster_name = cluster_name.split('/')[-1]
        
        # Extract service name from ARN
        service_name = project.ecsServiceArn
        if service_name and service_name.startswith('arn:aws:ecs:'):
            service_name = service_name.split('/')[-1]
        
        logger.info(f"Checking shell access for service: {service_name} in cluster: {cluster_name}")
        
        # List tasks for the service
        response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='RUNNING'
        )
        
        running_tasks = response.get('taskArns', [])
        
        if not running_tasks:
            logger.warning(f"No running tasks found for service {service_name} in cluster {cluster_name}")
            return {
                "available": False,
                "status": "no_tasks",
                "reason": "No running containers found",
                "taskCount": 0,
                "debug": {
                    "serviceName": service_name,
                    "clusterName": cluster_name,
                    "region": region
                }
            }
        
        # Get task details to find container names
        tasks_response = ecs_client.describe_tasks(
            cluster=cluster_name,
            tasks=running_tasks[:1]  # Just check the first task
        )
        
        if tasks_response['tasks']:
            task = tasks_response['tasks'][0]
            containers = [container['name'] for container in task.get('containers', [])]
            
            # Get the first container name (main container)
            container_name = containers[0] if containers else "app"
            
            return {
                "available": True,
                "status": "ready",
                "taskArn": task['taskArn'],
                "clusterArn": project.ecsClusterArn,  # Return the full cluster ARN
                "containerName": container_name,  # Added containerName
                "taskCount": len(running_tasks),
                "containers": containers,
                "region": region  # Add region info for frontend
            }
        else:
            return {
                "available": False,
                "status": "no_tasks",
                "reason": "No running containers found",
                "taskCount": 0
            }
            
    except ClientError as e:
        logger.error(f"Error checking ECS tasks: {e}")
        return {
            "available": False,
            "status": "error",
            "reason": f"Error checking container status: {e.response['Error']['Message']}"
        }
    except Exception as e:
        logger.error(f"Unexpected error checking shell availability: {e}")
        return {
            "available": False,
            "status": "error",
            "reason": f"Unexpected error: {str(e)}"
        }


@router.post("/{project_id}/exec/command")
async def execute_command(
    project_id: str,
    command_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Execute a command in the project container"""
    # Check if project exists and belongs to user
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
    
    # Check if project has ECS service (has been deployed at least once)
    if not project.ecsServiceArn:
        return {
            "success": False,
            "message": "Project must be deployed to execute commands"
        }
    
    command = command_data.get("command", "")
    if not command:
        return {
            "success": False,
            "message": "No command provided"
        }
    
    import os
    from botocore.exceptions import ClientError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        ecs_client = await create_aws_client(project, 'ecs', region)
        
        # Extract cluster ARN or use default
        cluster_arn = project.ecsClusterArn or "default"
        
        # Get a running task
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_arn,
            serviceName=project.ecsServiceArn,
            desiredStatus='RUNNING'
        )
        
        running_tasks = tasks_response.get('taskArns', [])
        if not running_tasks:
            return {
                "success": False,
                "message": "No running tasks found"
            }
        
        # Execute command on the first running task
        task_arn = running_tasks[0]
        
        # Get task details to find container name
        task_details = ecs_client.describe_tasks(
            cluster=cluster_arn,
            tasks=[task_arn]
        )
        
        if not task_details['tasks']:
            return {
                "success": False,
                "message": "Task not found"
            }
        
        # Get the first container name (usually the main app container)
        container_name = None
        for container in task_details['tasks'][0].get('containers', []):
            if container.get('name'):
                container_name = container['name']
                break
        
        if not container_name:
            return {
                "success": False,
                "message": "No container found in task"
            }
        
        # Execute command using ECS Exec
        exec_response = ecs_client.execute_command(
            cluster=cluster_arn,
            task=task_arn,
            container=container_name,
            command=command,
            interactive=True
        )
        
        return {
            "success": True,
            "sessionId": exec_response.get('session', {}).get('sessionId'),
            "streamUrl": exec_response.get('session', {}).get('streamUrl'),
            "tokenValue": exec_response.get('session', {}).get('tokenValue'),
            "taskArn": task_arn,
            "container": container_name
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'InvalidParameterException' and 'execute command' in error_message:
            return {
                "success": False,
                "message": "ECS Exec is not enabled for this service. Shell access requires ECS Exec to be enabled during deployment."
            }
        
        logger.error(f"Error executing command: {e}")
        return {
            "success": False,
            "message": f"Error executing command: {error_message}"
        }
    except Exception as e:
        logger.error(f"Unexpected error executing command: {e}")
        return {
            "success": False,
            "message": f"Unexpected error: {str(e)}"
        }


@router.get("/{project_id}/logs")
async def get_project_logs(
    project_id: str,
    limit: int = 100,
    hours_back: int = 1,
    current_user: User = Depends(get_current_user)
):
    """Get application logs for a project from CloudWatch"""
    # Check if project exists and belongs to user
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
    
    # Check if project has ever been deployed (has ECS service), not just current status
    if not project.ecsServiceArn:
        return {
            "logs": [],
            "message": "Project must be deployed to view application logs",
            "logGroupName": f"/ecs/{project.name}",
            "totalStreams": 0
        }
    
    # Fetch logs from CloudWatch
    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        logs_data = await cloudwatch_svc.get_project_logs(
            project_name=project.name,
            limit=limit,
            hours_back=hours_back
        )
        return logs_data
    except Exception as e:
        logger.error(f"Error fetching logs for project {project_id}: {str(e)}")
        return {
            "logs": [],
            "message": f"Error fetching logs: {str(e)}",
            "logGroupName": f"/ecs/{project.name}",
            "totalStreams": 0
        }


@router.get("/{project_id}/deployed-resources")
async def get_project_deployed_resources(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get information about deployed AWS resources for a project"""
    # Check if project exists and belongs to user
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

    
    try:
        # Get region from team config or environment
        region = os.getenv('AWS_REGION', 'us-east-1')
        team_credentials = await get_team_aws_credentials(project)
        if team_credentials and team_credentials.get('region'):
            region = team_credentials['region']
        
        # Initialize AWS clients
        ecs_client = await create_aws_client(project, 'ecs', region)
        ec2_client = await create_aws_client(project, 'ec2', region)
        elbv2_client = await create_aws_client(project, 'elbv2', region)
        
        result = {
            "vpc": None,
            "subnets": [],
            "cluster": None,
            "service": None,
            "loadBalancer": None
        }
        
        # If project has stored network configuration, use that
        if project.existingVpcId:
            try:
                vpc_response = ec2_client.describe_vpcs(VpcIds=[project.existingVpcId])
                if vpc_response['Vpcs']:
                    vpc = vpc_response['Vpcs'][0]
                    vpc_name = project.existingVpcId
                    for tag in vpc.get('Tags', []):
                        if tag['Key'] == 'Name':
                            vpc_name = tag['Value']
                            break
                    
                    result["vpc"] = {
                        "id": vpc['VpcId'],
                        "name": vpc_name,
                        "cidrBlock": vpc['CidrBlock']
                    }
            except ClientError:
                pass
        
        if project.existingSubnetIds:
            try:
                import json
                subnet_ids = json.loads(project.existingSubnetIds)
                if subnet_ids:
                    subnets_response = ec2_client.describe_subnets(SubnetIds=subnet_ids)
                    subnets = []
                    for subnet in subnets_response['Subnets']:
                        subnet_name = subnet['SubnetId']
                        for tag in subnet.get('Tags', []):
                            if tag['Key'] == 'Name':
                                subnet_name = tag['Value']
                                break
                        
                        subnets.append({
                            "id": subnet['SubnetId'],
                            "name": subnet_name,
                            "cidrBlock": subnet['CidrBlock'],
                            "availabilityZone": subnet['AvailabilityZone']
                        })
                    result["subnets"] = subnets
            except (ClientError, json.JSONDecodeError):
                pass
        
        if project.existingClusterArn:
            try:
                cluster_response = ecs_client.describe_clusters(clusters=[project.existingClusterArn])
                if cluster_response['clusters']:
                    cluster = cluster_response['clusters'][0]
                    result["cluster"] = {
                        "arn": cluster['clusterArn'],
                        "name": cluster['clusterName'],
                        "runningTasksCount": cluster['runningTasksCount'],
                        "activeServicesCount": cluster['activeServicesCount']
                    }
            except ClientError:
                pass
        
        # Try to find ECS service for this project
        if project.ecsServiceArn:
            try:
                service_response = ecs_client.describe_services(
                    cluster=project.existingClusterArn or "default",
                    services=[project.ecsServiceArn]
                )
                if service_response['services']:
                    service = service_response['services'][0]
                    result["service"] = {
                        "arn": service['serviceArn'],
                        "name": service['serviceName'],
                        "status": service['status'],
                        "runningCount": service['runningCount'],
                        "desiredCount": service['desiredCount']
                    }
            except ClientError:
                pass
        
        # Try to find load balancer for this project
        if project.albArn:
            try:
                lb_response = elbv2_client.describe_load_balancers(
                    LoadBalancerArns=[project.albArn]
                )
                if lb_response['LoadBalancers']:
                    lb = lb_response['LoadBalancers'][0]
                    result["loadBalancer"] = {
                        "arn": lb['LoadBalancerArn'],
                        "name": lb['LoadBalancerName'],
                        "dnsName": lb['DNSName'],
                        "scheme": lb['Scheme'],
                        "state": lb['State']['Code']
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
            "error": "AWS credentials not configured"
        }
    except Exception as e:
        logger.error(f"Error fetching deployed resources: {str(e)}")
        return {
            "vpc": None,
            "subnets": [],
            "cluster": None,
            "service": None,
            "loadBalancer": None,
            "error": f"Error fetching deployed resources: {str(e)}"
        }


@router.get("/{project_id}/debug-logs")
async def debug_project_logs(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Debug endpoint to see what log groups and streams exist"""
    # Check if project exists and belongs to user
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
    
    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        log_group_info = await cloudwatch_svc.get_log_group_info(project.name)
        return {
            "project_name": project.name,
            "expected_log_group": f"/ecs/{project.name}",
            "log_group_info": log_group_info
        }
    except Exception as e:
        return {
            "project_name": project.name,
            "expected_log_group": f"/ecs/{project.name}",
            "error": str(e)
        }


@router.post("/{project_id}/webhook/configure")
async def configure_webhook(
    project_id: str,
    github_access_token: Optional[str] = Header(None, alias="X-GitHub-Token"),
    current_user: User = Depends(get_current_user)
):
    """Configure webhook for automatic deployments"""
    # Check if project exists and belongs to user
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
    
    # Generate webhook secret if not exists
    if not project.webhookSecret:
        import secrets
        webhook_secret = secrets.token_urlsafe(32)
        
        await prisma.project.update(
            where={"id": project_id},
            data={"webhookSecret": webhook_secret}
        )
    else:
        webhook_secret = project.webhookSecret
    
    # Webhook URL
    base_url = settings.webhook_base_url or settings.backend_url
    webhook_url = f"{base_url}/api/webhook/github"
    
    # If GitHub access token provided, try to create webhook automatically
    if github_access_token:
        try:
            webhook_service = GitHubWebhookService()
            webhook_result = await webhook_service.create_webhook(
                git_repo_url=project.gitRepoUrl,
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                access_token=github_access_token
            )
            
            # Mark webhook as configured
            await prisma.project.update(
                where={"id": project_id},
                data={"webhookConfigured": True}
            )
            
            return {
                "webhookUrl": webhook_url,
                "webhookSecret": webhook_secret,
                "automatic": True,
                "webhookId": webhook_result.get("id"),
                "status": "created" if webhook_result.get("created") else "updated" if webhook_result.get("updated") else "exists"
            }
        except Exception as e:
            logger.error(f"Failed to automatically create webhook: {str(e)}")
            # Fall back to manual instructions
    
    # Return manual instructions
    return {
        "webhookUrl": webhook_url,
        "webhookSecret": webhook_secret,
        "automatic": False,
        "instructions": {
            "1": "Go to your GitHub repository settings",
            "2": "Click on 'Webhooks' in the left sidebar",
            "3": "Click 'Add webhook'",
            "4": f"Set Payload URL to: {webhook_url}",
            "5": "Set Content type to: application/json",
            "6": f"Set Secret to: {webhook_secret}",
            "7": "Select 'Just the push event'",
            "8": "Make sure 'Active' is checked",
            "9": "Click 'Add webhook'"
        }
    }


@router.delete("/{project_id}/webhook")
async def delete_webhook_config(
    project_id: str,
    github_access_token: Optional[str] = Header(None, alias="X-GitHub-Token"),
    current_user: User = Depends(get_current_user)
):
    """Delete webhook configuration"""
    # Check if project exists and belongs to user
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
    
    # If GitHub access token provided, try to delete webhook from GitHub
    if github_access_token and project.webhookSecret:
        try:
            base_url = settings.webhook_base_url or settings.backend_url
            webhook_url = f"{base_url}/api/webhook/github"
            webhook_service = GitHubWebhookService()
            await webhook_service.delete_webhook(
                git_repo_url=project.gitRepoUrl,
                webhook_url=webhook_url,
                access_token=github_access_token
            )
        except Exception as e:
            logger.error(f"Failed to delete webhook from GitHub: {str(e)}")
            # Continue with local deletion even if GitHub deletion fails
    
    # Remove webhook secret and disable auto-deploy
    await prisma.project.update(
        where={"id": project_id},
        data={
            "webhookSecret": None,
            "autoDeployEnabled": False,
            "webhookConfigured": False
        }
    )
    
    return {"message": "Webhook configuration deleted successfully"}


@router.get("/{project_id}/codebuild-logs")
async def get_project_codebuild_logs(
    project_id: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get CodeBuild logs for a project"""
    # Check if project exists and belongs to user
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
    
    # Fetch CodeBuild logs
    try:
        cloudwatch_svc = await create_cloudwatch_service(project)
        logs_data = await cloudwatch_svc.get_codebuild_logs(
            project_name=project.name,
            limit=limit
        )
        return logs_data
    except Exception as e:
        logger.error(f"Error fetching CodeBuild logs for project {project_id}: {str(e)}")
        return {
            "logs": [],
            "message": f"Error fetching CodeBuild logs: {str(e)}",
            "logGroupName": None,
            "totalStreams": 0
        }
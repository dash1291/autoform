from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import json
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import Project, ProjectCreate, ProjectUpdate, ProjectStatus, User
from services import cloudwatch_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Project])
async def get_projects(current_user: User = Depends(get_current_user)):
    """Get all projects for the current user"""
    logger.info(f"Getting projects for user: {current_user.id}")
    
    projects = await prisma.project.find_many(
        where={"userId": current_user.id},
        order={"createdAt": "desc"}
    )
    
    logger.info(f"Found {len(projects)} projects for user {current_user.id}")
    return projects


@router.post("/", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new project"""
    # Check if project name already exists for this user
    existing_project = await prisma.project.find_first(
        where={
            "userId": current_user.id,
            "name": project.name
        }
    )
    
    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A project with this name already exists"
        )
    
    # Create the project
    new_project = await prisma.project.create(
        data={
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
    )
    
    return new_project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a specific project"""
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
    
    return project


@router.put("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a project"""
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
    
    return updated_project


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
    
    # Check if project is deployed and has ECS service
    if project.status != "DEPLOYED" or not project.ecsServiceArn:
        return {
            "available": False,
            "status": "not_deployed",
            "reason": "Project must be deployed to access shell"
        }
    
    # Check if there are running tasks
    import boto3
    import os
    from botocore.exceptions import ClientError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        ecs_client = boto3.client('ecs', region_name=region)
        
        # Extract cluster ARN or use default
        cluster_arn = project.ecsClusterArn or "default"
        
        # List tasks for the service
        response = ecs_client.list_tasks(
            cluster=cluster_arn,
            serviceName=project.ecsServiceArn,
            desiredStatus='RUNNING'
        )
        
        running_tasks = response.get('taskArns', [])
        
        if not running_tasks:
            return {
                "available": False,
                "status": "no_tasks",
                "reason": "No running containers found",
                "taskCount": 0
            }
        
        # Get task details to find container names
        tasks_response = ecs_client.describe_tasks(
            cluster=cluster_arn,
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
                "clusterArn": cluster_arn,  # Changed from 'cluster' to 'clusterArn'
                "containerName": container_name,  # Added containerName
                "taskCount": len(running_tasks),
                "containers": containers
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
    
    # Check if project is deployed and has ECS service
    if project.status != "DEPLOYED" or not project.ecsServiceArn:
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
    
    import boto3
    import os
    from botocore.exceptions import ClientError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        ecs_client = boto3.client('ecs', region_name=region)
        
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
    
    # For non-deployed projects, show appropriate message
    if project.status != "DEPLOYED":
        return {
            "logs": [],
            "message": "Project must be deployed to view application logs",
            "logGroupName": f"/ecs/{project.name}",
            "totalStreams": 0
        }
    
    # Fetch logs from CloudWatch
    try:
        logs_data = await cloudwatch_service.get_project_logs(
            project_name=project.name,
            limit=limit
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
    
    # Implement AWS resource information fetching for deployed projects
    import boto3
    import os
    from botocore.exceptions import ClientError, NoCredentialsError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        # Initialize AWS clients
        ecs_client = boto3.client('ecs', region_name=region)
        ec2_client = boto3.client('ec2', region_name=region)
        elbv2_client = boto3.client('elbv2', region_name=region)
        
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
        log_group_info = await cloudwatch_service.get_log_group_info(project.name)
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
        logs_data = await cloudwatch_service.get_codebuild_logs(
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
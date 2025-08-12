from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
import logging
import boto3

from core.database import get_async_session
from core.security import get_current_user
from schemas import User, ProjectStatus, TeamMemberRole, EnvironmentStatus
from sqlmodel import select, and_
from sqlmodel.ext.asyncio.session import AsyncSession
from models.project import Project
from models.team import Team, TeamMember, TeamAwsConfig
from models.environment import Environment
from models.deployment import Deployment
from services.encryption_service import encryption_service
from services.deployment import DeploymentService
from infrastructure.services.acm_service import ACMService
from utils.aws_client import create_client

logger = logging.getLogger(__name__)

router = APIRouter()


async def update_ecs_service_instance_count(
    environment: Environment,
    desired_count: int,
    session: AsyncSession
) -> Dict[str, Any]:
    """Update the ECS service instance count for a deployed environment."""
    
    # Validate instance count
    if not isinstance(desired_count, int) or desired_count < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="desiredInstanceCount must be a non-negative integer"
        )
    
    if desired_count > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="desiredInstanceCount cannot exceed 10 instances"
        )
    
    # Update the environment model
    environment.desired_instance_count = desired_count
    
    # If environment is not deployed, just save the desired count
    if not (environment.ecs_service_arn and environment.ecs_cluster_arn):
        return {
            "instanceCountUpdated": True,
            "message": f"Instance count will be set to {desired_count} when deployed",
            "desiredCount": desired_count,
            "status": "NOT_DEPLOYED"
        }
    
    # Environment is deployed, update the ECS service
    try:
        # Get AWS credentials
        team_aws_config = await session.get(TeamAwsConfig, environment.team_aws_config_id)
        if not team_aws_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS configuration not found for environment"
            )
        
        # Decrypt credentials
        access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
        secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)
        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
        
        # Update ECS service
        ecs_client = create_client("ecs", team_aws_config.aws_region, aws_credentials)
        
        # Extract service name and cluster name from ARNs
        service_name = environment.ecs_service_arn.split("/")[-1]
        cluster_name = environment.ecs_cluster_arn.split("/")[-1]
        
        # Update the service's desired count
        response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=desired_count
        )
        
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            return {
                "instanceCountUpdated": True,
                "message": f"Instance count updated to {desired_count}",
                "desiredCount": desired_count,
                "status": "UPDATING"
            }
        else:
            raise Exception("Failed to update ECS service")
        
    except Exception as e:
        logger.error(f"Error updating ECS service instance count: {e}")
        # Still save the desired count in DB even if ECS update fails
        return {
            "instanceCountUpdated": False,
            "message": f"Instance count saved but ECS update failed: {str(e)}",
            "desiredCount": desired_count,
            "status": "ERROR"
        }


@router.get("/projects/{project_id}/environments")
async def get_project_environments(
    project_id: str, current_user: User = Depends(get_current_user)
):
    """Get all environments for a project"""
    async with get_async_session() as session:
        # Verify project access
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Check team access
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify user has access
        has_access = team.owner_id == current_user.id
        if not has_access:
            member_result = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None
            
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )

        # Get all environments for this project
        environments = await session.execute(
            select(Environment).where(Environment.project_id == project_id)
            .order_by(Environment.created_at.asc())
        )

        environments_response = []
        for env in environments.scalars().all():
            # Get AWS config info
            aws_config = await session.get(TeamAwsConfig, env.team_aws_config_id)
            aws_config_info = {
                "type": "team",
                "id": aws_config.id if aws_config else None,
                "name": aws_config.name if aws_config else None,
                "region": aws_config.aws_region if aws_config else None,
            }

            # Get latest deployment
            latest_deployment_result = await session.execute(
                select(Deployment).where(Deployment.environment_id == env.id)
                .order_by(Deployment.created_at.desc())
                .limit(1)
            )
            latest_deployment = latest_deployment_result.scalar_one_or_none()

            environments_response.append(
                {
                    "id": env.id,
                    "name": env.name,
                    "branch": env.branch,
                    "status": env.status,
                    "domain": env.custom_domain,
                    "albDns": env.domain,
                    "certificateArn": env.certificate_arn,
                    "existingVpcId": env.existing_vpc_id,
                    "existingSubnetIds": env.existing_subnet_ids,
                    "existingClusterArn": env.existing_cluster_arn,
                    "cpu": env.cpu,
                    "memory": env.memory,
                    "diskSize": env.disk_size,
                    "desiredInstanceCount": env.desired_instance_count if hasattr(env, 'desired_instance_count') else 1,
                    "subdirectory": project.subdirectory,
                    "port": project.port,
                    "healthCheckPath": project.health_check_path,
                    "awsConfig": aws_config_info,
                    "latestDeployment": {
                        "id": latest_deployment.id,
                        "status": latest_deployment.status,
                        "createdAt": latest_deployment.created_at,
                    }
                    if latest_deployment
                    else None,
                    "createdAt": env.created_at,
                    "updatedAt": env.updated_at,
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

    async with get_async_session() as session:
        # Verify project access (all projects belong to teams)
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        
        # Get team info
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        
        # Check if user has access (owner or admin)
        has_access = team.owner_id == current_user.id
        if not has_access:
            # Check if user is team admin
            admin_member_result = await session.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.team_id == project.team_id,
                        TeamMember.user_id == current_user.id,
                        TeamMember.role == TeamMemberRole.ADMIN
                    )
                )
            )
            has_access = admin_member_result.scalar_one_or_none() is not None
            
        if not has_access:
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
        existing_env_result = await session.execute(
            select(Environment).where(
                and_(Environment.project_id == project_id, Environment.name == name)
            )
        )
        existing_env = existing_env_result.scalar_one_or_none()

        if existing_env:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Environment with name '{name}' already exists for this project",
            )

        # Verify team AWS config exists and user has access (all projects are team projects now)
        team_aws_config_result = await session.execute(
            select(TeamAwsConfig).where(
                and_(TeamAwsConfig.id == aws_config_id, TeamAwsConfig.team_id == project.team_id)
            )
        )
        team_aws_config = team_aws_config_result.scalar_one_or_none()

        if not team_aws_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team AWS configuration not found",
            )

        # Create environment
        new_environment = Environment(
            project_id=project_id,
            name=name,
            team_aws_config_id=aws_config_id,
            branch=environment_data.get("branch", "main"),
            cpu=environment_data.get("cpu", 256),
            memory=environment_data.get("memory", 512),
            disk_size=environment_data.get("diskSize", 21),
            existing_vpc_id=environment_data.get("existingVpcId"),
            existing_subnet_ids=environment_data.get("existingSubnetIds"),
            existing_cluster_arn=environment_data.get("existingClusterArn"),
            custom_domain=environment_data.get("domain"),
            auto_provision_certificate=environment_data.get("autoProvisionCertificate", True),
            use_route53_validation=environment_data.get("useRoute53Validation", False),
            status=EnvironmentStatus.CREATED,
        )
        
        session.add(new_environment)
        await session.commit()
        await session.refresh(new_environment)

        logger.info(
            f"Environment '{name}' created for project {project_id} by {current_user.id}"
        )

        return {
            "message": f"Environment '{name}' created successfully",
            "id": new_environment.id,
            "name": new_environment.name,
            "awsConfig": {"type": "team", "name": team_aws_config.name},
        }


@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get a specific environment with full details"""

    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access to the project (all projects are team projects now)
        has_access = team.owner_id == current_user.id
        if not has_access:
            member_result = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )
        
        # Get team AWS config
        team_aws_config = await session.get(TeamAwsConfig, environment.team_aws_config_id)
        if not team_aws_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="AWS config not found"
            )
        
        # Get deployments (latest 10)
        deployments_result = await session.execute(
            select(Deployment).where(Deployment.environment_id == environment.id)
            .order_by(Deployment.created_at.desc())
            .limit(10)
        )
        deployments = deployments_result.scalars().all()

        # Prepare AWS config info
        aws_config_info = {
            "type": "team",
            "id": team_aws_config.id,
            "name": team_aws_config.name,
            "region": team_aws_config.aws_region,
        }

        return {
            "id": environment.id,
            "name": environment.name,
            "projectId": environment.project_id,
            "projectName": project.name,
            "branch": environment.branch,
            "status": environment.status,
            "ecsClusterArn": environment.ecs_cluster_arn,
            "ecsServiceArn": environment.ecs_service_arn,
            "albArn": environment.alb_arn,
            "domain": environment.custom_domain,
            "albDns": environment.custom_domain,
            "existingVpcId": environment.existing_vpc_id,
            "existingSubnetIds": environment.existing_subnet_ids,
            "existingClusterArn": environment.existing_cluster_arn,
            "cpu": environment.cpu,
            "memory": environment.memory,
            "diskSize": environment.disk_size,
            "subdirectory": project.subdirectory,
            "port": project.port,
            "healthCheckPath": project.health_check_path,
            "secretsArn": project.secrets_arn,
            "awsConfig": aws_config_info,
            "deployments": [
                {
                    "id": deployment.id,
                    "status": deployment.status,
                    "imageTag": deployment.image_tag,
                    "commitSha": deployment.commit_sha,
                    "createdAt": deployment.created_at,
                }
                for deployment in deployments
            ],
            "createdAt": environment.created_at,
            "updatedAt": environment.updated_at,
        }


@router.put("/environments/{environment_id}")
async def update_environment(
    environment_id: str,
    environment_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update an environment"""

    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Check if environment is deployed - if so, block infrastructure resource changes
        # AWS credentials can be updated (for rotation/account switching)
        is_deployed = environment.status == "DEPLOYED" or environment.ecs_service_arn is not None
        protected_fields = {"existingVpcId", "existingSubnetIds", "existingClusterArn", "cpu", "memory", "diskSize"}
        
        if is_deployed and any(field in environment_data for field in protected_fields):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify infrastructure resource settings (VPC, subnets, cluster, CPU, memory, disk) for deployed environments. AWS credentials and domain settings can still be updated."
            )
        
        # Get project
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access (must be team owner or team admin)
        has_admin_access = team.owner_id == current_user.id
        if not has_admin_access:
            admin_member_result = await session.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.team_id == project.team_id,
                        TeamMember.user_id == current_user.id,
                        TeamMember.role == TeamMemberRole.ADMIN
                    )
                )
            )
            has_admin_access = admin_member_result.scalar_one_or_none() is not None
        
        if not has_admin_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin permissions required.",
            )

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
                existing_env_result = await session.execute(
                    select(Environment).where(
                        and_(
                            Environment.project_id == environment.project_id,
                            Environment.name == name,
                            Environment.id != environment_id
                        )
                    )
                )
                existing_env = existing_env_result.scalar_one_or_none()
                if existing_env:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Environment with name '{name}' already exists for this project",
                    )

            environment.name = name

        # AWS config update
        if "awsConfigId" in environment_data and "awsConfigType" in environment_data:
            aws_config_id = environment_data["awsConfigId"].strip()
            aws_config_type = environment_data["awsConfigType"].strip()

            if aws_config_type == "team":
                team_aws_config_result = await session.execute(
                    select(TeamAwsConfig).where(
                        and_(TeamAwsConfig.id == aws_config_id, TeamAwsConfig.team_id == project.team_id)
                    )
                )
                team_aws_config = team_aws_config_result.scalar_one_or_none()

                if not team_aws_config:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Team AWS configuration not found",
                    )

                environment.team_aws_config_id = aws_config_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid AWS config type. Only 'team' configs are supported.",
                )

        # Other configuration updates
        if "branch" in environment_data:
            environment.branch = environment_data["branch"]
        if "cpu" in environment_data:
            environment.cpu = environment_data["cpu"]
        if "memory" in environment_data:
            environment.memory = environment_data["memory"]
        if "diskSize" in environment_data:
            environment.disk_size = environment_data["diskSize"]
        if "existingVpcId" in environment_data:
            environment.existing_vpc_id = environment_data["existingVpcId"]
        if "existingSubnetIds" in environment_data:
            environment.existing_subnet_ids = environment_data["existingSubnetIds"]
        if "existingClusterArn" in environment_data:
            environment.existing_cluster_arn = environment_data["existingClusterArn"]
        if "domain" in environment_data:
            environment.custom_domain = environment_data["domain"]
        if "autoProvisionCertificate" in environment_data:
            environment.auto_provision_certificate = environment_data["autoProvisionCertificate"]
        if "useRoute53Validation" in environment_data:
            environment.use_route53_validation = environment_data["useRoute53Validation"]
        
        # Handle desired instance count update
        ecs_update_response = None
        if "desiredInstanceCount" in environment_data:
            desired_count = environment_data["desiredInstanceCount"]
            ecs_update_response = await update_ecs_service_instance_count(
                environment, desired_count, session
            )

        # Handle certificate provisioning if domain settings changed
        certificate_info = None
        if environment.custom_domain and environment.auto_provision_certificate:
            try:
                # Get team AWS credentials
                team_aws_config = await session.get(TeamAwsConfig, environment.team_aws_config_id)
                aws_credentials = None
                if team_aws_config:
                    # Decrypt team credentials
                    access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
                    secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)
                    
                    if access_key and secret_key:
                        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
                
                # Initialize ACM service
                acm_service = ACMService(
                    project_name=environment.name,
                    domain_name=environment.custom_domain,
                    region=team_aws_config.aws_region if team_aws_config else "us-east-1",
                    aws_credentials=aws_credentials,
                    use_route53_validation=environment.use_route53_validation,
                )
                
                # Try to get or create certificate (don't wait for validation to avoid blocking)
                certificate_arn = await acm_service.get_or_create_certificate(wait_for_validation=False)
                environment.certificate_arn = certificate_arn
                
                certificate_status = await acm_service.get_certificate_status()
                
                certificate_info = {
                    "certificateArn": certificate_arn,
                    "status": "provisioned" if certificate_status == "ISSUED" else "pending_validation",
                    "certificateStatus": certificate_status
                }
                
                logger.info(f"Certificate status for {environment.custom_domain}: {certificate_status}, use_route53: {environment.use_route53_validation}")
                logger.info(f"Validation records available: {len(acm_service.validation_records) if acm_service.validation_records else 0}")
                
                # If certificate is pending validation, provide appropriate instructions
                if certificate_status == "PENDING_VALIDATION":
                    if environment.use_route53_validation:
                        certificate_info.update({
                            "validationRequired": "automatic",
                            "validationRecords": acm_service.validation_records,
                            "domain": environment.custom_domain,
                            "instructions": {
                                "step1": "Route53 validation is in progress",
                                "step2": "Certificate validation typically completes within 15 minutes", 
                                "step3": "If Route53 validation fails, you may need to add the DNS records manually"
                            }
                        })
                    else:
                        certificate_info.update({
                            "validationRequired": "manual",
                            "validationRecords": acm_service.validation_records,
                            "domain": environment.custom_domain,
                            "instructions": {
                                "step1": "Add the CNAME validation records to your DNS provider",
                                "step2": f"Add a CNAME record pointing {environment.custom_domain} to your load balancer (if deployed)",
                                "step3": "Certificate validation typically completes within 15 minutes"
                            }
                        })
                
                logger.info(f"Certificate requested for {environment.custom_domain}: {certificate_arn}, Status: {certificate_status}")
                
            except Exception as e:
                logger.error(f"Failed to provision certificate for {environment.custom_domain}: {e}")
                certificate_info = {
                    "error": str(e),
                    "status": "failed",
                    "validationRequired": "manual" if not environment.use_route53_validation else "automatic"
                }

        # Save changes
        session.add(environment)
        await session.commit()
        await session.refresh(environment)

        logger.info(f"Environment {environment_id} updated by {current_user.id}")

        response = {
            "message": f"Environment '{environment.name}' updated successfully",
            "id": environment.id,
            "name": environment.name,
        }
        
        if certificate_info:
            response["certificate"] = certificate_info
        
        if ecs_update_response:
            response["instanceCount"] = ecs_update_response
            
        return response


@router.delete("/environments/{environment_id}")
async def delete_environment(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an environment"""

    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access (must be team owner or team admin)
        has_admin_access = team.owner_id == current_user.id
        if not has_admin_access:
            admin_member_result = await session.execute(
                select(TeamMember).where(
                    and_(
                        TeamMember.team_id == project.team_id,
                        TeamMember.user_id == current_user.id,
                        TeamMember.role == TeamMemberRole.ADMIN
                    )
                )
            )
            has_admin_access = admin_member_result.scalar_one_or_none() is not None
        
        if not has_admin_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin permissions required.",
            )

        # Check if environment is currently deployed (has active AWS resources)
        if environment.status == ProjectStatus.DEPLOYED or environment.ecs_service_arn:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete a deployed environment. Please undeploy it first.",
            )

        # Delete environment (this will cascade delete deployments and environment variables)
        await session.delete(environment)
        await session.commit()

        logger.info(
            f"Environment {environment_id} ('{environment.name}') deleted by {current_user.id}"
        )

        return {"message": f"Environment '{environment.name}' deleted successfully"}


@router.get("/environments/{environment_id}/certificate-status")
async def get_certificate_status(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get the current certificate status for an environment"""
    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project and verify access
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
        
        # Verify access
        has_access = team.owner_id == current_user.id
        if not has_access:
            member_result = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )
        
        # If no domain configured, return not applicable
        if not environment.custom_domain:
            return {
                "status": "not_applicable",
                "message": "HTTPS not configured for this environment"
            }
        
        # If no certificate ARN, return pending
        if not environment.certificate_arn:
            return {
                "status": "not_requested",
                "message": "SSL certificate not yet requested"
            }
        
        try:
            # Get team AWS credentials
            team_aws_config = await session.get(TeamAwsConfig, environment.team_aws_config_id)
            if not team_aws_config:
                return {
                    "status": "error",
                    "message": "No AWS credentials configured"
                }
            
            # Decrypt team credentials
            access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
            secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)
            
            if not access_key or not secret_key:
                return {
                    "status": "error", 
                    "message": "Invalid AWS credentials"
                }
            
            aws_credentials = {"access_key": access_key, "secret_key": secret_key}
            
            # Check certificate status using ACM service
            acm_service = ACMService(
                project_name=environment.name,
                domain_name=environment.custom_domain,
                region=team_aws_config.aws_region,
                aws_credentials=aws_credentials,
                use_route53_validation=environment.use_route53_validation,
            )
            
            # Set the certificate ARN so we can check its status
            acm_service.certificate_arn = environment.certificate_arn
            certificate_status = await acm_service.get_certificate_status()
            
            if certificate_status == "ISSUED":
                return {
                    "status": "ready",
                    "message": "SSL certificate is active and ready"
                }
            elif certificate_status == "PENDING_VALIDATION":
                logger.info(f"Certificate is pending validation for {environment.custom_domain}")
                logger.info(f"use_route53_validation: {environment.use_route53_validation}")
                
                # Always try to get validation records when pending
                validation_records = None
                try:
                    validation_records = await acm_service.get_certificate_validation_records()
                    logger.info(f"Got {len(validation_records) if validation_records else 0} validation records")
                except Exception as e:
                    logger.error(f"Error getting validation records: {e}")
                
                response = {
                    "status": "pending_validation",
                    "message": "SSL certificate is pending DNS validation"
                }
                
                # Always set validation type based on use_route53_validation setting
                response["validationRequired"] = "manual" if not environment.use_route53_validation else "automatic"
                
                if validation_records:
                    response["validationRecords"] = validation_records
                elif not environment.use_route53_validation:
                    # For manual validation, we should have records. Log if we don't
                    logger.warning(f"No validation records found for manual validation of {environment.custom_domain}")
                    
                return response
            elif certificate_status == "FAILED":
                return {
                    "status": "failed",
                    "message": "SSL certificate validation failed"
                }
            else:
                return {
                    "status": "unknown",
                    "message": f"SSL certificate status: {certificate_status}"
                }
                
        except Exception as e:
            logger.error(f"Error checking certificate status: {e}")
            return {
                "status": "error",
                "message": "Failed to check certificate status"
            }


@router.get("/environments/{environment_id}/available-aws-configs")
async def get_available_aws_configs(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get available AWS configurations for an environment"""

    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access (all projects belong to teams)
        has_access = team.owner_id == current_user.id
        if not has_access:
            member_result = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            )

        available_configs = {"teamConfigs": []}

        # Get team AWS configs (all projects belong to teams)
        team_configs_result = await session.execute(
            select(TeamAwsConfig).where(
                and_(TeamAwsConfig.team_id == project.team_id, TeamAwsConfig.is_active == True)
            )
        )
        team_configs = team_configs_result.scalars().all()

        for config in team_configs:
            available_configs["teamConfigs"].append(
                {
                    "id": config.id,
                    "name": config.name,
                    "region": config.aws_region,
                    "type": "team",
                }
            )

        return available_configs


@router.get("/{environment_id}/service-status")
async def get_environment_service_status(
    environment_id: str, current_user: User = Depends(get_current_user)
):
    """Get the actual ECS service status and health for a specific environment"""
    async with get_async_session() as session:
        # Get environment
        environment = await session.get(Environment, environment_id)
        if not environment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get project
        project = await session.get(Project, environment.project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
            )
        
        # Get team
        team = await session.get(Team, project.team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
            )
        
        # Verify access
        has_access = team.owner_id == current_user.id
        if not has_access:
            member_result = await session.execute(
                select(TeamMember).where(
                    and_(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id)
                )
            )
            has_access = member_result.scalar_one_or_none() is not None
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Environment not found"
            )
        
        # Get team AWS config
        team_aws_config = await session.get(TeamAwsConfig, environment.team_aws_config_id)

        # Check if environment has been deployed
        if not environment.ecs_service_arn or not environment.ecs_cluster_arn:
            return {
                "status": "NOT_DEPLOYED",
                "message": "Environment has not been deployed yet",
                "service": None,
                "failureReasons": [],
                "crashLoopDetected": False,
            }

        try:
            # Get team AWS credentials for this environment
            if not team_aws_config:
                return {
                    "status": "ERROR",
                    "message": "No AWS credentials configured for this environment",
                    "service": None,
                    "failureReasons": ["No AWS credentials configured"],
                    "crashLoopDetected": False,
                }

            # Decrypt credentials
            access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
            secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)
            aws_credentials = {"access_key": access_key, "secret_key": secret_key}
            
            # Create deployment service to check status
            deployment_service = DeploymentService(
                region=team_aws_config.aws_region, 
                aws_credentials=aws_credentials
            )

            # Get service status
            service_arn = environment.ecs_service_arn
            cluster_arn = environment.ecs_cluster_arn
            
            # Extract service name and cluster name from ARNs
            service_name = service_arn.split("/")[-1]
            cluster_name = cluster_arn.split("/")[-1]

            # Use the same logic as project service status
            ecs_client = create_client("ecs", team_aws_config.aws_region, aws_credentials)

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



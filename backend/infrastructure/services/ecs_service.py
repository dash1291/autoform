import boto3
import json
import logging
from typing import List, Dict, Any

from infrastructure.types import EnvironmentVariable

logger = logging.getLogger(__name__)


class ECSService:
    def __init__(
        self,
        project_name: str,
        environment_variables: List[EnvironmentVariable],
        cpu: int,
        memory: int,
        disk_size: int,
        image_uri: str,
        container_port: int = 3000,
        region: str = "us-east-1",
        existing_cluster_arn: str = None,
        vpc_id: str = "",
        subnet_ids: List[str] = None,
        security_group_id: str = "",
        execution_role_arn: str = "",
        task_role_arn: str = "",
        target_group_arn: str = "",
        aws_credentials=None
    ):
        self.project_name = project_name
        self.environment_variables = environment_variables
        self.cpu = cpu
        self.memory = memory
        self.disk_size = disk_size
        self.image_uri = image_uri
        self.container_port = container_port
        self.region = region
        self.existing_cluster_arn = existing_cluster_arn
        self.vpc_id = vpc_id
        self.subnet_ids = subnet_ids or []
        self.security_group_id = security_group_id
        self.execution_role_arn = execution_role_arn
        self.task_role_arn = task_role_arn
        self.target_group_arn = target_group_arn
        self.aws_credentials = aws_credentials
        
        # Initialize AWS clients with custom credentials if provided
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update({
                "aws_access_key_id": aws_credentials["access_key"],
                "aws_secret_access_key": aws_credentials["secret_key"]
            })
        
        self.ecs = boto3.client("ecs", **client_config)
        self.secretsmanager = boto3.client("secretsmanager", **client_config)
        self.sts = boto3.client("sts", **client_config)
        
        self.cluster_arn: str = ""
        self.service_arn: str = ""
        self.task_definition_arn: str = ""
    
    async def initialize(self):
        """Initialize ECS resources"""
        # Set up or find ECS cluster
        self.cluster_arn = await self._create_or_find_cluster()
        
        # Create task definition
        self.task_definition_arn = await self._create_task_definition()
        
        # Create or update ECS service
        self.service_arn = await self._create_or_update_service()
    
    async def _create_or_find_cluster(self) -> str:
        """Create or find ECS cluster"""
        if self.existing_cluster_arn:
            logger.info(f"Using existing cluster: {self.existing_cluster_arn}")
            return self.existing_cluster_arn
        
        cluster_name = f"{self.project_name}-cluster"
        
        try:
            # Check if cluster exists
            response = self.ecs.describe_clusters(clusters=[cluster_name])
            
            if response["clusters"] and len(response["clusters"]) > 0:
                cluster = response["clusters"][0]
                if cluster.get("clusterName") and cluster.get("status") == "ACTIVE":
                    logger.info(f"Found existing ECS cluster: {cluster['clusterArn']}")
                    return cluster["clusterArn"]
            
            logger.info("No existing ECS cluster found, creating new one")
        except Exception as error:
            logger.info(f"Error checking for existing cluster, creating new one: {error}")
        
        # Create new cluster
        response = self.ecs.create_cluster(
            clusterName=cluster_name,
            tags=[{"key": "Name", "value": cluster_name}]
        )
        
        cluster_arn = response["cluster"]["clusterArn"]
        logger.info(f"Created ECS cluster: {cluster_arn}")
        return cluster_arn
    
    async def _create_task_definition(self) -> str:
        """Create ECS task definition"""
        # Prepare environment variables and secrets
        environment = []
        secrets = []
        
        for env_var in self.environment_variables:
            if env_var.is_secret and env_var.secret_key:
                # Add to secrets array for AWS Secrets Manager
                secret_arn = await self._get_secret_arn(env_var.secret_key)
                secrets.append({
                    "name": env_var.key,
                    "valueFrom": secret_arn
                })
            elif not env_var.is_secret and env_var.value:
                # Add to environment array for regular environment variables
                environment.append({
                    "name": env_var.key,
                    "value": env_var.value
                })
        
        container_def = {
            "name": self.project_name,
            "image": self.image_uri,
            "portMappings": [{
                "containerPort": self.container_port,
                "protocol": "tcp"
            }],
            "essential": True,
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": f"/ecs/{self.project_name}",
                    "awslogs-region": self.region,
                    "awslogs-stream-prefix": "ecs"
                }
            }
        }
        
        # Add environment variables if any
        if environment:
            container_def["environment"] = environment
        
        # Add secrets if any
        if secrets:
            container_def["secrets"] = secrets
        
        family_name = f"{self.project_name}-task"
        
        response = self.ecs.register_task_definition(
            family=family_name,
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu=str(self.cpu),
            memory=str(self.memory),
            ephemeralStorage={"sizeInGiB": self.disk_size},
            executionRoleArn=self.execution_role_arn,
            taskRoleArn=self.task_role_arn,
            containerDefinitions=[container_def],
            tags=[{"key": "Name", "value": family_name}]
        )
        
        task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
        logger.info(f"Created task definition: {task_def_arn}")
        return task_def_arn
    
    async def _create_or_update_service(self) -> str:
        """Create or update ECS service"""
        service_name = f"{self.project_name}-service"
        
        try:
            # Check if service already exists
            response = self.ecs.describe_services(
                cluster=self.cluster_arn,
                services=[service_name]
            )
            
            if response["services"] and len(response["services"]) > 0:
                existing_service = response["services"][0]
                
                if existing_service.get("status") == "ACTIVE":
                    logger.info(f"Updating existing ECS service: {existing_service['serviceArn']}")
                    
                    # Update the service with new task definition
                    update_response = self.ecs.update_service(
                        cluster=self.cluster_arn,
                        service=service_name,
                        taskDefinition=self.task_definition_arn,
                        desiredCount=1,
                        enableExecuteCommand=True
                    )
                    
                    logger.info("Service updated successfully")
                    return update_response["service"]["serviceArn"]
        except Exception as error:
            logger.info("No existing service found or error checking, creating new service")
        
        # Create new service
        response = self.ecs.create_service(
            serviceName=service_name,
            cluster=self.cluster_arn,
            taskDefinition=self.task_definition_arn,
            desiredCount=1,
            launchType="FARGATE",
            enableExecuteCommand=True,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": self.subnet_ids,
                    "securityGroups": [self.security_group_id],
                    "assignPublicIp": "ENABLED"
                }
            },
            loadBalancers=[{
                "targetGroupArn": self.target_group_arn,
                "containerName": self.project_name,
                "containerPort": self.container_port
            }],
            tags=[{"key": "Name", "value": service_name}]
        )
        
        service_arn = response["service"]["serviceArn"]
        logger.info(f"ECS service created: {service_arn}")
        return service_arn
    
    async def _get_account_id(self) -> str:
        """Get AWS account ID"""
        response = self.sts.get_caller_identity()
        return response["Account"]
    
    async def _get_secret_arn(self, secret_name: str) -> str:
        """Get ARN for a secret in AWS Secrets Manager"""
        try:
            response = self.secretsmanager.describe_secret(SecretId=secret_name)
            
            if not response.get("ARN"):
                raise Exception(f"Could not get ARN for secret: {secret_name}")
            
            return response["ARN"]
        except Exception as error:
            logger.error(f"Failed to get secret ARN for {secret_name}: {error}")
            # Fallback to constructed ARN (though this might not work)
            account_id = await self._get_account_id()
            return f"arn:aws:secretsmanager:{self.region}:{account_id}:secret:{secret_name}"
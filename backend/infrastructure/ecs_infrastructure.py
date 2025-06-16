import boto3
import logging
from typing import List

from infrastructure.types import ECSInfrastructureArgs, ECSInfrastructureOutput, EnvironmentVariable
from infrastructure.services.vpc_service import VPCService
from infrastructure.services.iam_service import IAMService
from infrastructure.services.load_balancer_service import LoadBalancerService
from infrastructure.services.ecs_service import ECSService

logger = logging.getLogger(__name__)


class ECSInfrastructure:
    def __init__(self, args: ECSInfrastructureArgs, aws_credentials=None):
        import os
        self.region = args.region or os.getenv('AWS_REGION', 'us-east-1')
        self.project_name = args.project_name
        self.image_uri = args.image_uri
        self.container_port = args.container_port or 3000
        self.health_check_path = args.health_check_path or "/"
        self.cpu = args.cpu or 256
        self.memory = args.memory or 512
        self.disk_size = args.disk_size or 21
        self.args = args
        self.aws_credentials = aws_credentials
        
        # Initialize AWS clients with custom credentials if provided
        client_config = {"region_name": self.region}
        if aws_credentials:
            client_config.update({
                "aws_access_key_id": aws_credentials["access_key"],
                "aws_secret_access_key": aws_credentials["secret_key"]
            })
        
        self.logs = boto3.client("logs", **client_config)
        
        # Service instances will be initialized during setup
        self.vpc_service: VPCService = None
        self.iam_service: IAMService = None
        self.load_balancer_service: LoadBalancerService = None
        self.ecs_service: ECSService = None
    
    async def create_or_update_infrastructure(self) -> ECSInfrastructureOutput:
        """Create or update the complete ECS infrastructure"""
        try:
            logger.info("Starting infrastructure setup...")
            
            # Initialize VPC service
            self.vpc_service = VPCService(
                project_name=self.project_name,
                environment_variables=self.args.environment_variables or [],
                region=self.region,
                existing_vpc_id=self.args.existing_vpc_id,
                existing_subnet_ids=self.args.existing_subnet_ids,
                aws_credentials=self.aws_credentials
            )
            await self.vpc_service.initialize()
            
            # Initialize IAM service
            self.iam_service = IAMService(
                project_name=self.project_name,
                region=self.region,
                aws_credentials=self.aws_credentials
            )
            await self.iam_service.initialize()
            
            # CloudWatch log group - Ensure it exists
            await self._create_or_update_log_group()
            
            # Initialize load balancer service
            self.load_balancer_service = LoadBalancerService(
                project_name=self.project_name,
                region=self.region,
                vpc_id=self.vpc_service.vpc_id,
                subnet_ids=self.vpc_service.subnet_ids,
                security_group_id=self.vpc_service.security_group_ids.alb_security_group_id,
                container_port=self.container_port,
                health_check_path=self.health_check_path,
                aws_credentials=self.aws_credentials
            )
            await self.load_balancer_service.initialize()
            
            # Initialize ECS service
            self.ecs_service = ECSService(
                project_name=self.project_name,
                environment_variables=self.args.environment_variables or [],
                cpu=self.cpu,
                memory=self.memory,
                disk_size=self.disk_size,
                image_uri=self.image_uri,
                container_port=self.container_port,
                region=self.region,
                existing_cluster_arn=self.args.existing_cluster_arn,
                vpc_id=self.vpc_service.vpc_id,
                subnet_ids=self.vpc_service.subnet_ids,
                security_group_id=self.vpc_service.security_group_ids.ecs_security_group_id,
                execution_role_arn=self.iam_service.execution_role_arn,
                task_role_arn=self.iam_service.task_role_arn,
                target_group_arn=self.load_balancer_service.target_group_arn,
                aws_credentials=self.aws_credentials
            )
            await self.ecs_service.initialize()
            
            logger.info("✅ Infrastructure setup complete!")
            
            return ECSInfrastructureOutput(
                cluster_arn=self.ecs_service.cluster_arn,
                service_arn=self.ecs_service.service_arn,
                load_balancer_arn=self.load_balancer_service.load_balancer_arn,
                load_balancer_dns=self.load_balancer_service.load_balancer_dns
            )
            
        except Exception as error:
            logger.error(f"Error creating/updating infrastructure: {error}")
            raise error
    
    async def _create_or_update_log_group(self):
        """Create or update CloudWatch log group"""
        log_group_name = f"/ecs/{self.project_name}"
        
        try:
            # Check if log group exists
            response = self.logs.describe_log_groups(
                logGroupNamePrefix=log_group_name
            )
            
            # Check if the exact log group exists in the response
            existing_log_group = None
            if response.get("logGroups"):
                existing_log_group = next(
                    (lg for lg in response["logGroups"] if lg["logGroupName"] == log_group_name),
                    None
                )
            
            if existing_log_group:
                logger.info(f"Found existing log group: {log_group_name}")
                return
            
            # Log group doesn't exist, create it
            logger.info(f"Creating new log group: {log_group_name}")
            
            self.logs.create_log_group(
                logGroupName=log_group_name,
                tags={"Name": f"{self.project_name}-logs"}
            )
            
            self.logs.put_retention_policy(
                logGroupName=log_group_name,
                retentionInDays=7
            )
            
            logger.info(f"✅ Created log group: {log_group_name}")
            
        except Exception as error:
            logger.error(f"Error managing log group: {error}")
            # Try to create it anyway
            try:
                logger.info(f"Attempting to create log group: {log_group_name}")
                
                self.logs.create_log_group(
                    logGroupName=log_group_name,
                    tags={"Name": f"{self.project_name}-logs"}
                )
                
                self.logs.put_retention_policy(
                    logGroupName=log_group_name,
                    retentionInDays=7
                )
                
                logger.info(f"✅ Created log group: {log_group_name}")
            except Exception as create_error:
                logger.error(f"Failed to create log group: {create_error}")
                raise create_error
    
    async def destroy_infrastructure(self):
        """Destroy the infrastructure (placeholder for future implementation)"""
        logger.info("Infrastructure destruction would need to be implemented")
        # TODO: Implement infrastructure cleanup
        pass
import boto3
import logging
from typing import List

from infrastructure.types import (
    ECSInfrastructureArgs,
    ECSInfrastructureOutput,
    EnvironmentVariable,
)
from infrastructure.services.vpc_service import VPCService
from infrastructure.services.iam_service import IAMService
from infrastructure.services.load_balancer_service import LoadBalancerService
from infrastructure.services.ecs_service import ECSService

logger = logging.getLogger(__name__)


class ECSInfrastructure:
    def __init__(self, args: ECSInfrastructureArgs, aws_credentials=None):
        import os

        self.region = args.region or os.getenv("AWS_REGION", "us-east-1")
        self.project_name = args.project_name
        self.image_uri = args.image_uri
        self.container_port = args.container_port or 3000
        self.health_check_path = args.health_check_path or "/"
        self.cpu = args.cpu or 256
        self.memory = args.memory or 512
        self.disk_size = args.disk_size or 21
        self.args = args
        self.aws_credentials = aws_credentials

        # Initialize AWS clients with LocalStack support
        from utils.aws_client import create_client
        
        self.logs = create_client("logs", self.region, aws_credentials)
        self.ecs = create_client("ecs", self.region, aws_credentials)

        # Service instances will be initialized during setup
        self.vpc_service: VPCService = None
        self.iam_service: IAMService = None
        self.load_balancer_service: LoadBalancerService = None
        self.ecs_service: ECSService = None

    async def create_infrastructure_foundation(self) -> dict:
        """Create infrastructure foundation (VPC, cluster, IAM, ALB) without ECS service"""
        logger.info("Creating infrastructure foundation...")
        
        # Initialize VPC service
        self.vpc_service = VPCService(
            project_name=self.project_name,
            environment_variables=self.args.environment_variables or [],
            region=self.region,
            project_id=self.args.project_id,
            existing_vpc_id=self.args.existing_vpc_id,
            existing_subnet_ids=self.args.existing_subnet_ids,
            aws_credentials=self.aws_credentials,
        )
        await self.vpc_service.initialize()

        # Initialize IAM service
        self.iam_service = IAMService(
            project_name=self.project_name,
            region=self.region,
            aws_credentials=self.aws_credentials,
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
            launch_type=self.args.launch_type,
            aws_credentials=self.aws_credentials,
        )
        lb_result = await self.load_balancer_service.initialize()
        
        # Update subnet IDs if they were corrected by the load balancer service
        if lb_result and "corrected_subnet_ids" in lb_result:
            corrected_subnets = lb_result["corrected_subnet_ids"]
            if corrected_subnets != self.vpc_service.subnet_ids:
                logger.warning(f"⚠️  Updating VPC subnet configuration to match existing ALB")
                logger.warning(f"   Original subnets: {self.vpc_service.subnet_ids}")
                logger.warning(f"   Corrected subnets: {corrected_subnets}")
                self.vpc_service.subnet_ids = corrected_subnets
        
        # Initialize and create ECS cluster and capacity provider (if EC2)
        cluster_arn = None
        if not self.args.existing_cluster_arn:
            cluster_name = f"{self.project_name}-cluster"
            try:
                # Check if cluster exists
                response = self.ecs.describe_clusters(clusters=[cluster_name])
                if response["clusters"] and len(response["clusters"]) > 0:
                    cluster = response["clusters"][0]
                    if cluster.get("clusterName") and cluster.get("status") == "ACTIVE":
                        logger.info(f"Found existing ECS cluster: {cluster['clusterArn']}")
                        cluster_arn = cluster["clusterArn"]
                else:
                    logger.info("No existing ECS cluster found, creating new one")
                    response = self.ecs.create_cluster(
                        clusterName=cluster_name, 
                        tags=[{"key": "Name", "value": cluster_name}]
                    )
                    cluster_arn = response["cluster"]["clusterArn"]
                    logger.info(f"Created ECS cluster: {cluster_arn}")
            except Exception as error:
                logger.info(f"Error checking for existing cluster, creating new one: {error}")
                response = self.ecs.create_cluster(
                    clusterName=cluster_name, 
                    tags=[{"key": "Name", "value": cluster_name}]
                )
                cluster_arn = response["cluster"]["clusterArn"]
                logger.info(f"Created ECS cluster: {cluster_arn}")
        else:
            cluster_arn = self.args.existing_cluster_arn
        
        # If EC2 launch type, create capacity provider
        capacity_provider_result = None
        if self.args.launch_type == "EC2":
            from infrastructure.services.ec2_capacity_provider import EC2CapacityProvider
            
            cluster_name = cluster_arn.split("/")[-1] if "/" in cluster_arn else cluster_arn
            
            ec2_provider = EC2CapacityProvider(
                project_name=self.project_name,
                cluster_name=cluster_name,
                vpc_id=self.vpc_service.vpc_id,
                subnet_ids=self.vpc_service.subnet_ids,
                instance_type=self.args.ec2_instance_type,
                min_size=self.args.ec2_min_size,
                max_size=self.args.ec2_max_size,
                desired_capacity=self.args.ec2_desired_capacity,
                use_spot=self.args.ec2_use_spot,
                spot_max_price=self.args.ec2_spot_max_price,
                key_name=self.args.ec2_key_name,
                target_capacity=self.args.capacity_provider_target_capacity,
                region=self.region,
                aws_credentials=self.aws_credentials,
            )
            
            capacity_provider_result = await ec2_provider.setup_ec2_capacity()
            
            # Add ALB security group rules
            if self.vpc_service.security_group_ids.alb_security_group_id:
                logger.info("Adding ALB security group rules to EC2 instances...")
                ec2_provider.add_alb_security_group_rule(
                    capacity_provider_result["security_group_id"], 
                    self.vpc_service.security_group_ids.alb_security_group_id
                )
        
        logger.info("✅ Infrastructure foundation created successfully!")
        
        return {
            "vpc_id": self.vpc_service.vpc_id,
            "subnet_ids": self.vpc_service.subnet_ids,
            "security_group_ids": self.vpc_service.security_group_ids,
            "execution_role_arn": self.iam_service.execution_role_arn,
            "task_role_arn": self.iam_service.task_role_arn,
            "load_balancer_arn": self.load_balancer_service.load_balancer_arn,
            "load_balancer_dns": self.load_balancer_service.load_balancer_dns,
            "target_group_arn": self.load_balancer_service.target_group_arn,
            "cluster_arn": cluster_arn,
            "capacity_provider_name": capacity_provider_result.get("capacity_provider_name") if capacity_provider_result else None,
        }

    async def create_ecs_service_with_foundation(self, foundation_resources: dict) -> None:
        """Create ECS service using pre-created foundation resources"""
        logger.info("Creating ECS service with pre-created foundation...")
        
        # Set the pre-created resources
        self.vpc_service = type('obj', (object,), {
            'vpc_id': foundation_resources['vpc_id'],
            'subnet_ids': foundation_resources['subnet_ids'],
            'security_group_ids': foundation_resources['security_group_ids']
        })
        self.iam_service = type('obj', (object,), {
            'execution_role_arn': foundation_resources['execution_role_arn'],
            'task_role_arn': foundation_resources['task_role_arn']
        })
        self.load_balancer_service = type('obj', (object,), {
            'target_group_arn': foundation_resources['target_group_arn'],
            'load_balancer_arn': foundation_resources['load_balancer_arn'],
            'load_balancer_dns': foundation_resources['load_balancer_dns'],
            'load_balancer_name': self.project_name,
        })
        
        # Initialize ECS service with pre-created resources
        self.ecs_service = ECSService(
            project_name=self.project_name,
            environment_variables=self.args.environment_variables or [],
            cpu=self.cpu,
            memory=self.memory,
            disk_size=self.disk_size,
            image_uri=self.image_uri,
            container_port=self.container_port,
            region=self.region,
            existing_cluster_arn=foundation_resources.get('cluster_arn', self.args.existing_cluster_arn),
            vpc_id=foundation_resources['vpc_id'],
            subnet_ids=foundation_resources['subnet_ids'],
            security_group_id=foundation_resources['security_group_ids'].ecs_security_group_id,
            execution_role_arn=foundation_resources['execution_role_arn'],
            task_role_arn=foundation_resources['task_role_arn'],
            target_group_arn=foundation_resources['target_group_arn'],
            aws_credentials=self.aws_credentials,
            launch_type=self.args.launch_type,
            ec2_instance_type=self.args.ec2_instance_type,
            ec2_min_size=self.args.ec2_min_size,
            ec2_max_size=self.args.ec2_max_size,
            ec2_desired_capacity=self.args.ec2_desired_capacity,
            ec2_use_spot=self.args.ec2_use_spot,
            ec2_spot_max_price=self.args.ec2_spot_max_price,
            ec2_key_name=self.args.ec2_key_name,
            capacity_provider_target_capacity=self.args.capacity_provider_target_capacity,
            alb_security_group_id=foundation_resources['security_group_ids'].alb_security_group_id,
        )
        
        # For EC2 launch type, set the capacity provider name if available
        if self.args.launch_type == "EC2" and foundation_resources.get('capacity_provider_name'):
            self.ecs_service.capacity_provider_name = foundation_resources['capacity_provider_name']
        
        await self.ecs_service.initialize()
        
        logger.info("✅ ECS service created successfully!")

    async def create_or_update_infrastructure(self, pre_created_foundation: dict = None) -> ECSInfrastructureOutput:
        """Create or update the complete ECS infrastructure"""
        try:
            logger.info("Starting infrastructure setup...")
            logger.info(f"🔍 ECS Infrastructure Args - existing_vpc_id: '{self.args.existing_vpc_id}', existing_subnet_ids: {self.args.existing_subnet_ids}")

            # Initialize VPC service
            self.vpc_service = VPCService(
                project_name=self.project_name,
                environment_variables=self.args.environment_variables or [],
                region=self.region,
                project_id=self.args.project_id,
                existing_vpc_id=self.args.existing_vpc_id,
                existing_subnet_ids=self.args.existing_subnet_ids,
                aws_credentials=self.aws_credentials,
            )
            await self.vpc_service.initialize()

            # Initialize IAM service
            self.iam_service = IAMService(
                project_name=self.project_name,
                region=self.region,
                aws_credentials=self.aws_credentials,
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
                launch_type=self.args.launch_type,
                aws_credentials=self.aws_credentials,
            )
            lb_result = await self.load_balancer_service.initialize()
            
            # Update subnet IDs if they were corrected by the load balancer service
            if lb_result and "corrected_subnet_ids" in lb_result:
                corrected_subnets = lb_result["corrected_subnet_ids"]
                if corrected_subnets != self.vpc_service.subnet_ids:
                    logger.warning(f"⚠️  Updating VPC subnet configuration to match existing ALB")
                    logger.warning(f"   Original subnets: {self.vpc_service.subnet_ids}")
                    logger.warning(f"   Corrected subnets: {corrected_subnets}")
                    self.vpc_service.subnet_ids = corrected_subnets

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
                aws_credentials=self.aws_credentials,
                launch_type=self.args.launch_type,
                ec2_instance_type=self.args.ec2_instance_type,
                ec2_min_size=self.args.ec2_min_size,
                ec2_max_size=self.args.ec2_max_size,
                ec2_desired_capacity=self.args.ec2_desired_capacity,
                ec2_use_spot=self.args.ec2_use_spot,
                ec2_spot_max_price=self.args.ec2_spot_max_price,
                ec2_key_name=self.args.ec2_key_name,
                capacity_provider_target_capacity=self.args.capacity_provider_target_capacity,
                alb_security_group_id=self.vpc_service.security_group_ids.alb_security_group_id,
            )
            await self.ecs_service.initialize()

            logger.info("✅ Infrastructure setup complete!")

            return ECSInfrastructureOutput(
                cluster_arn=self.ecs_service.cluster_arn,
                service_arn=self.ecs_service.service_arn,
                load_balancer_arn=self.load_balancer_service.load_balancer_arn,
                load_balancer_dns=self.load_balancer_service.load_balancer_dns,
                load_balancer_name=self.load_balancer_service.load_balancer_name,
                vpc_id=self.vpc_service.vpc_id,
                subnet_ids=self.vpc_service.subnet_ids,
            )

        except Exception as error:
            logger.error(f"Error creating/updating infrastructure: {error}")
            raise error

    async def _create_or_update_log_group(self):
        """Create or update CloudWatch log group"""
        log_group_name = f"/ecs/{self.project_name}"

        try:
            # Check if log group exists
            response = self.logs.describe_log_groups(logGroupNamePrefix=log_group_name)

            # Check if the exact log group exists in the response
            existing_log_group = None
            if response.get("logGroups"):
                existing_log_group = next(
                    (
                        lg
                        for lg in response["logGroups"]
                        if lg["logGroupName"] == log_group_name
                    ),
                    None,
                )

            if existing_log_group:
                logger.info(f"Found existing log group: {log_group_name}")
                return

            # Log group doesn't exist, create it
            logger.info(f"Creating new log group: {log_group_name}")

            self.logs.create_log_group(
                logGroupName=log_group_name, tags={"Name": f"{self.project_name}-logs"}
            )

            self.logs.put_retention_policy(
                logGroupName=log_group_name, retentionInDays=7
            )

            logger.info(f"✅ Created log group: {log_group_name}")

        except Exception as error:
            logger.error(f"Error managing log group: {error}")
            # Try to create it anyway
            try:
                logger.info(f"Attempting to create log group: {log_group_name}")

                self.logs.create_log_group(
                    logGroupName=log_group_name,
                    tags={"Name": f"{self.project_name}-logs"},
                )

                self.logs.put_retention_policy(
                    logGroupName=log_group_name, retentionInDays=7
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

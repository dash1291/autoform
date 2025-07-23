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
        aws_credentials=None,
        launch_type: str = "EC2",
        ec2_instance_type: str = "t3a.medium",
        ec2_min_size: int = 1,
        ec2_max_size: int = 3,
        ec2_desired_capacity: int = 1,
        ec2_use_spot: bool = True,
        ec2_spot_max_price: str = "",
        ec2_key_name: str = "",
        capacity_provider_target_capacity: int = 80,
        alb_security_group_id: str = "",
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
        self.launch_type = launch_type
        self.ec2_instance_type = ec2_instance_type
        self.ec2_min_size = ec2_min_size
        self.ec2_max_size = ec2_max_size
        self.ec2_desired_capacity = ec2_desired_capacity
        self.ec2_use_spot = ec2_use_spot
        self.ec2_spot_max_price = ec2_spot_max_price
        self.ec2_key_name = ec2_key_name
        self.capacity_provider_target_capacity = capacity_provider_target_capacity
        self.alb_security_group_id = alb_security_group_id
        self.capacity_provider_name = None

        # Initialize AWS clients with custom credentials if provided
        from utils.aws_client import create_client
        
        self.ecs = create_client("ecs", region, aws_credentials)
        self.secretsmanager = create_client("secretsmanager", region, aws_credentials)
        self.sts = create_client("sts", region, aws_credentials)

        self.cluster_arn: str = ""
        self.service_arn: str = ""
        self.task_definition_arn: str = ""

    async def initialize(self):
        """Initialize ECS resources"""
        # Set up or find ECS cluster
        self.cluster_arn = await self._create_or_find_cluster()
        
        # Set up EC2 capacity provider if using EC2 launch type
        if self.launch_type == "EC2":
            await self._setup_ec2_capacity_provider()

        # Check for existing service configuration BEFORE creating task definition
        await self._check_existing_service_config()

        # Create task definition (will use detected container name/port if found)
        self.task_definition_arn = await self._create_task_definition()

        # Create or update ECS service
        self.service_arn = await self._create_or_update_service()
    
    async def _setup_ec2_capacity_provider(self):
        """Set up EC2 capacity provider for the cluster (only if needed)"""
        from infrastructure.services.ec2_capacity_provider import EC2CapacityProvider
        
        # Extract cluster name from ARN
        cluster_name = self.cluster_arn.split("/")[-1] if "/" in self.cluster_arn else self.cluster_arn
        
        # Check if using existing cluster with existing capacity provider
        if self.existing_cluster_arn:
            logger.info(f"Using existing cluster: {cluster_name}")
            existing_cp_name = await self._check_existing_capacity_provider(cluster_name)
            if existing_cp_name:
                self.capacity_provider_name = existing_cp_name
                logger.info(f"Using existing capacity provider: {existing_cp_name}")
                return
        
        # Create new capacity provider for new or unconfigured cluster
        logger.info("Setting up new EC2 capacity provider...")
        
        ec2_provider = EC2CapacityProvider(
            project_name=self.project_name,  # Use original project name for IAM resources
            cluster_name=cluster_name,
            vpc_id=self.vpc_id,
            subnet_ids=self.subnet_ids,
            instance_type=self.ec2_instance_type,
            min_size=self.ec2_min_size,
            max_size=self.ec2_max_size,
            desired_capacity=self.ec2_desired_capacity,
            use_spot=self.ec2_use_spot,
            spot_max_price=self.ec2_spot_max_price,
            key_name=self.ec2_key_name,
            target_capacity=self.capacity_provider_target_capacity,
            region=self.region,
            aws_credentials=self.aws_credentials,
        )
        
        result = await ec2_provider.setup_ec2_capacity()
        self.capacity_provider_name = result["capacity_provider_name"]
        
        # Add ALB security group rules if ALB security group ID is provided
        if self.alb_security_group_id:
            logger.info("Adding ALB security group rules to EC2 instances...")
            ec2_provider.add_alb_security_group_rule(
                result["security_group_id"], 
                self.alb_security_group_id
            )
        
        logger.info(f"EC2 capacity provider setup complete: {self.capacity_provider_name}")
    
    async def _check_existing_capacity_provider(self, cluster_name: str) -> str:
        """Check if cluster already has an EC2 capacity provider"""
        try:
            response = self.ecs.describe_clusters(
                clusters=[cluster_name],
                include=['CAPACITY_PROVIDERS']
            )
            
            if response['clusters']:
                cluster = response['clusters'][0]
                capacity_providers = cluster.get('capacityProviders', [])
                
                # Look for EC2 capacity provider (not FARGATE/FARGATE_SPOT)
                for cp in capacity_providers:
                    if cp not in ['FARGATE', 'FARGATE_SPOT']:
                        return cp
            
            return None
        except Exception as e:
            logger.warning(f"Could not check existing capacity providers: {e}")
            return None
    
    def _build_service_update_params(self, service_name: str, container_name: str) -> dict:
        """Build parameters for updating ECS service"""
        params = {
            "cluster": self.cluster_arn,
            "service": service_name,
            "taskDefinition": self.task_definition_arn,
            "desiredCount": 1,
            "enableExecuteCommand": True,
            "loadBalancers": [
                {
                    "targetGroupArn": self.target_group_arn,
                    "containerName": container_name,
                    "containerPort": self.container_port,
                }
            ],
        }
        
        # Add network configuration only for Fargate/awsvpc mode
        if self.launch_type == "FARGATE":
            network_config = {
                "subnets": self.subnet_ids,
                "securityGroups": [self.security_group_id],
                "assignPublicIp": "ENABLED"
            }
            params["networkConfiguration"] = {
                "awsvpcConfiguration": network_config
            }
        
        # Add capacity provider strategy for EC2
        if self.launch_type == "EC2" and self.capacity_provider_name:
            params["capacityProviderStrategy"] = [
                {"capacityProvider": self.capacity_provider_name, "weight": 1, "base": 0}
            ]
            # Add placement strategy for EC2 to optimize instance utilization
            params["placementStrategy"] = [
                {
                    "type": "binpack",
                    "field": "MEMORY"
                }
            ]
        
        return params

    async def _check_existing_service_config(self):
        """Check if service exists and get its container name"""
        service_name = f"{self.project_name}-service"

        try:
            response = self.ecs.describe_services(
                cluster=self.cluster_arn, services=[service_name]
            )

            services = response.get("services", [])
            if services and len(services) > 0:
                existing_service = services[0]
                if existing_service.get("status") in ["ACTIVE", "DRAINING", "PENDING"]:
                    task_def_arn = existing_service.get("taskDefinition")
                    if task_def_arn:
                        task_def_response = self.ecs.describe_task_definition(
                            taskDefinition=task_def_arn
                        )

                        containers = task_def_response.get("taskDefinition", {}).get(
                            "containerDefinitions", []
                        )
                        if containers:
                            container_name = containers[0].get("name")
                            if container_name:
                                self._existing_container_name = container_name
        except Exception as e:
            # Continue with defaults if service doesn't exist
            pass

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
            logger.info(
                f"Error checking for existing cluster, creating new one: {error}"
            )

        # Create new cluster
        response = self.ecs.create_cluster(
            clusterName=cluster_name, tags=[{"key": "Name", "value": cluster_name}]
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
                secrets.append({"name": env_var.key, "valueFrom": secret_arn})
            elif not env_var.is_secret and env_var.value:
                # Add to environment array for regular environment variables
                environment.append({"name": env_var.key, "value": env_var.value})

        # Use the detected container name if we found an existing service
        container_name = (
            getattr(self, "_existing_container_name", None) or self.project_name
        )

        # Configure port mappings based on network mode
        if self.launch_type == "EC2":
            # Bridge mode: Use dynamic port allocation
            port_mappings = [{"containerPort": self.container_port, "hostPort": 0, "protocol": "tcp"}]
            network_mode = "bridge"
        else:
            # Fargate: Use awsvpc mode
            port_mappings = [{"containerPort": self.container_port, "protocol": "tcp"}]
            network_mode = "awsvpc"

        container_def = {
            "name": container_name,
            "image": self.image_uri,
            "portMappings": port_mappings,
            "essential": True,
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": f"/ecs/{self.project_name}",
                    "awslogs-region": self.region,
                    "awslogs-stream-prefix": "ecs",
                },
            },
        }
        
        # Add memory and CPU at container level for EC2
        if self.launch_type == "EC2":
            container_def["memory"] = self.memory
            container_def["cpu"] = self.cpu

        # Add environment variables if any
        if environment:
            container_def["environment"] = environment

        # Add secrets if any
        if secrets:
            container_def["secrets"] = secrets

        family_name = f"{self.project_name}-task"

        # Build task definition parameters
        task_def_params = {
            "family": family_name,
            "networkMode": network_mode,
            "requiresCompatibilities": [self.launch_type],
            "executionRoleArn": self.execution_role_arn,
            "taskRoleArn": self.task_role_arn,
            "containerDefinitions": [container_def],
            "tags": [{"key": "Name", "value": family_name}],
        }
        
        # Add Fargate-specific parameters
        if self.launch_type == "FARGATE":
            task_def_params["cpu"] = str(self.cpu)
            task_def_params["memory"] = str(self.memory)
            task_def_params["ephemeralStorage"] = {"sizeInGiB": self.disk_size}
        
        response = self.ecs.register_task_definition(**task_def_params)

        task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
        logger.info(f"Created task definition: {task_def_arn}")
        return task_def_arn

    async def _create_or_update_service(self) -> str:
        """Create or update ECS service"""
        service_name = f"{self.project_name}-service"
        service_exists = False

        try:
            # Check if service already exists
            response = self.ecs.describe_services(
                cluster=self.cluster_arn, services=[service_name]
            )

            # Check if any services were returned (including inactive ones)
            services = response.get("services", [])

            if services and len(services) > 0:
                existing_service = services[0]
                service_status = existing_service.get("status")
                service_exists = True

                logger.info(f"Found existing service with status: {service_status}")

                # Try to update any existing service, regardless of status
                logger.info(
                    f"Attempting to update existing service: {existing_service.get('serviceArn', 'unknown arn')}"
                )
                try:
                    container_name = (
                        getattr(self, "_existing_container_name", None)
                        or self.project_name
                    )
                    update_params = self._build_service_update_params(service_name, container_name)
                    update_response = self.ecs.update_service(**update_params)
                    logger.info("Service updated successfully")
                    return update_response["service"]["serviceArn"]
                except Exception as update_error:
                    logger.warning(
                        f"Failed to update existing service: {str(update_error)}"
                    )

                # If we get here, the initial update attempt failed
                logger.info(
                    "Initial update failed, checking if we need to wait for service to stabilize..."
                )

                if service_status in ["DRAINING", "PENDING"]:
                    logger.info(
                        f"Service is {service_status}. Waiting for it to stabilize..."
                    )
                    try:
                        # Wait for the service to stabilize before trying again
                        waiter = self.ecs.get_waiter("services_stable")
                        waiter.wait(
                            cluster=self.cluster_arn,
                            services=[service_name],
                            WaiterConfig={"maxAttempts": 10, "delay": 30},
                        )

                        # Try to update the service after waiting
                        container_name = (
                            getattr(self, "_existing_container_name", None)
                            or self.project_name
                        )
                        update_params = self._build_service_update_params(service_name, container_name)
                        update_response = self.ecs.update_service(**update_params)

                        logger.info("Service updated after stabilization")
                        return update_response["service"]["serviceArn"]
                    except Exception as stabilize_error:
                        logger.warning(
                            f"Failed to update service after stabilization: {str(stabilize_error)}"
                        )
                        return None
                # If all update attempts failed, we have a configuration problem - don't try to create new service
                logger.error(
                    "All update attempts failed. Cannot create new service when one already exists."
                )
                raise Exception(
                    "Service update failed due to configuration mismatch. Service already exists and cannot be updated."
                )
        except Exception as error:
            logger.error(f"Error checking existing service: {str(error)}")
            logger.info("Attempting to list ALL services in cluster to debug...")
            try:
                all_services = self.ecs.list_services(cluster=self.cluster_arn)
                logger.info(f"All services in cluster: {all_services}")

                # Check if our service is in the list
                service_arns = all_services.get("serviceArns", [])
                matching_services = [arn for arn in service_arns if service_name in arn]
                logger.info(f"Services matching {service_name}: {matching_services}")

                if matching_services:
                    logger.info("Found matching service! Trying to update it...")
                    try:
                        container_name = (
                            getattr(self, "_existing_container_name", None)
                            or self.project_name
                        )
                        update_params = self._build_service_update_params(service_name, container_name)
                        update_response = self.ecs.update_service(**update_params)
                        logger.info(
                            "Successfully updated service found via list_services"
                        )
                        return update_response["service"]["serviceArn"]
                    except Exception as list_update_error:
                        logger.error(
                            f"Failed to update service found via list: {str(list_update_error)}"
                        )
            except Exception as list_error:
                logger.error(f"Failed to list services: {str(list_error)}")

        # Only create service if one doesn't exist
        if service_exists:
            logger.error("Cannot create new service - one already exists!")
            raise Exception(
                "Service already exists but all update attempts failed. Cannot create duplicate service."
            )

        logger.info(f"No existing service found. Creating new service: {service_name}")
        logger.info(f"DEBUG: Launch type is: {self.launch_type}")
        try:
            # Build service parameters
            service_params = {
                "serviceName": service_name,
                "cluster": self.cluster_arn,
                "taskDefinition": self.task_definition_arn,
                "desiredCount": 1,
                "enableExecuteCommand": True,
                "loadBalancers": [
                    {
                        "targetGroupArn": self.target_group_arn,
                        "containerName": getattr(self, "_existing_container_name", None)
                        or self.project_name,
                        "containerPort": self.container_port,
                    }
                ],
                "tags": [{"key": "Name", "value": service_name}],
            }
            
            # Add network configuration only for Fargate/awsvpc mode
            if self.launch_type == "FARGATE":
                network_config = {
                    "subnets": self.subnet_ids,
                    "securityGroups": [self.security_group_id],
                    "assignPublicIp": "ENABLED"
                }
                service_params["networkConfiguration"] = {
                    "awsvpcConfiguration": network_config
                }
                logger.info(f"DEBUG: Added networkConfiguration for Fargate")
            else:
                logger.info(f"DEBUG: Using bridge mode for {self.launch_type} - no networkConfiguration")
            
            # Add launch type specific parameters
            if self.launch_type == "FARGATE":
                service_params["launchType"] = "FARGATE"
            elif self.launch_type == "EC2" and self.capacity_provider_name:
                service_params["capacityProviderStrategy"] = [
                    {"capacityProvider": self.capacity_provider_name, "weight": 1, "base": 0}
                ]
                # Add placement strategy for EC2 to optimize instance utilization
                service_params["placementStrategy"] = [
                    {
                        "type": "binpack",
                        "field": "MEMORY"
                    }
                ]
            
            # Debug: Log the actual parameters being sent
            logger.info(f"DEBUG: Creating service with launch_type: {self.launch_type}")
            if 'networkConfiguration' in service_params:
                network_cfg = service_params['networkConfiguration']['awsvpcConfiguration']
                logger.info(f"DEBUG: Network config: {network_cfg}")
                logger.info(f"DEBUG: Has assignPublicIp: {'assignPublicIp' in network_cfg}")
            else:
                logger.info(f"DEBUG: No networkConfiguration (using bridge mode)")
            logger.info(f"DEBUG: Capacity provider: {service_params.get('capacityProviderStrategy', 'None')}")
            
            response = self.ecs.create_service(**service_params)

            service_arn = response["service"]["serviceArn"]
            logger.info(f"ECS service created: {service_arn}")
            return service_arn

        except Exception as create_error:
            if "not idempotent" in str(create_error).lower():
                logger.info(
                    "Service creation failed due to existing service. Attempting to update instead..."
                )

                # First, let's get info about the existing service
                try:
                    existing_service_info = self.ecs.describe_services(
                        cluster=self.cluster_arn, services=[service_name]
                    )
                    if existing_service_info.get("services"):
                        existing_service = existing_service_info["services"][0]
                        existing_task_def_arn = existing_service.get("taskDefinition")
                        logger.info(
                            f"Existing service uses task definition: {existing_task_def_arn}"
                        )

                        # Get the existing task definition to see the container name
                        if existing_task_def_arn:
                            existing_task_def = self.ecs.describe_task_definition(
                                taskDefinition=existing_task_def_arn
                            )
                            containers = existing_task_def.get(
                                "taskDefinition", {}
                            ).get("containerDefinitions", [])
                            if containers:
                                existing_container_name = containers[0].get("name")
                                existing_port_mappings = containers[0].get(
                                    "portMappings", []
                                )
                                logger.info(
                                    f"Existing container name: {existing_container_name}"
                                )
                                logger.info(
                                    f"Existing port mappings: {existing_port_mappings}"
                                )

                                # Use the existing container's port if different from what we expect
                                if (
                                    existing_port_mappings
                                    and len(existing_port_mappings) > 0
                                ):
                                    existing_port = existing_port_mappings[0].get(
                                        "containerPort"
                                    )
                                    if (
                                        existing_port
                                        and existing_port != self.container_port
                                    ):
                                        logger.info(
                                            f"Using existing container port {existing_port} instead of {self.container_port}"
                                        )
                                        self.container_port = existing_port
                except Exception as info_error:
                    logger.warning(
                        f"Could not get existing service info: {str(info_error)}"
                    )

                # Try to update the existing service with new task definition
                try:
                    logger.info(
                        f"Updating existing service with new task definition..."
                    )
                    logger.info(f"Task definition ARN: {self.task_definition_arn}")

                    # Update service with new task definition AND load balancer config
                    container_name = (
                        getattr(self, "_existing_container_name", None)
                        or self.project_name
                    )
                    update_params = self._build_service_update_params(service_name, container_name)
                    update_response = self.ecs.update_service(**update_params)
                    logger.info("Successfully updated existing service")
                    return update_response["service"]["serviceArn"]
                except Exception as update_error:
                    logger.error(
                        f"Failed to update existing service: {str(update_error)}"
                    )
                    raise create_error
            else:
                logger.error(f"Service creation failed: {str(create_error)}")
                raise create_error

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

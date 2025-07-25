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

        # Check for existing service configuration BEFORE creating task definition
        await self._check_existing_service_config()

        # Create task definition (will use detected container name/port if found)
        self.task_definition_arn = await self._create_task_definition()

        # Create or update ECS service
        self.service_arn = await self._create_or_update_service()
        
        # Validate that we got a valid service ARN
        if not self.service_arn:
            raise Exception("Failed to create or update ECS service: service_arn is None")

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

        container_def = {
            "name": container_name,
            "image": self.image_uri,
            "portMappings": [{"containerPort": self.container_port, "protocol": "tcp"}],
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
            tags=[{"key": "Name", "value": family_name}],
        )

        task_def_arn = response["taskDefinition"]["taskDefinitionArn"]
        logger.info(f"Created task definition: {task_def_arn}")
        return task_def_arn

    async def _create_or_update_service(self) -> str:
        """Create or update ECS service"""
        service_name = f"{self.project_name}-service"
        service_exists = False
        
        logger.info(f"Starting service creation/update for: {service_name}")

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
                
                # If service is INACTIVE, we should delete it and create a new one
                if service_status == "INACTIVE":
                    logger.info(f"Service is INACTIVE, deleting it to create a fresh one...")
                    try:
                        self.ecs.delete_service(
                            cluster=self.cluster_arn,
                            service=service_name,
                            force=True
                        )
                        import time
                        time.sleep(5)
                        logger.info("Successfully deleted INACTIVE service")
                        service_exists = False
                        # Exit early and let the code fall through to service creation
                    except Exception as delete_inactive_error:
                        logger.error(f"Failed to delete INACTIVE service: {str(delete_inactive_error)}")
                        # Continue with normal flow
                
                if service_exists:
                    # Try to update any existing service, regardless of status
                    logger.info(
                        f"Attempting to update existing service: {existing_service.get('serviceArn', 'unknown arn')}"
                    )
                    try:
                        container_name = (
                            getattr(self, "_existing_container_name", None)
                            or self.project_name
                        )
                        update_response = self.ecs.update_service(
                            cluster=self.cluster_arn,
                            service=service_name,
                            taskDefinition=self.task_definition_arn,
                            desiredCount=1,
                            enableExecuteCommand=True,
                            loadBalancers=[
                                {
                                    "targetGroupArn": self.target_group_arn,
                                    "containerName": container_name,
                                    "containerPort": self.container_port,
                                }
                            ],
                        )
                        service_arn = update_response["service"]["serviceArn"]
                        logger.info(f"Service updated successfully: {service_arn}")
                        logger.info(f"Returning service ARN: {service_arn}")
                        return service_arn
                    except Exception as update_error:
                        logger.error(
                            f"Failed to update existing service: {str(update_error)}"
                        )
                        logger.error(f"Update error type: {type(update_error).__name__}")
                        # Log more details about the service state
                        logger.error(f"Service ARN: {existing_service.get('serviceArn', 'unknown')}")
                        logger.error(f"Service status: {existing_service.get('status', 'unknown')}")
                        logger.error(f"Task definition: {existing_service.get('taskDefinition', 'unknown')}")
                        logger.error(f"Load balancers: {existing_service.get('loadBalancers', [])}")

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
                        update_response = self.ecs.update_service(
                            cluster=self.cluster_arn,
                            service=service_name,
                            taskDefinition=self.task_definition_arn,
                            desiredCount=1,
                            enableExecuteCommand=True,
                            loadBalancers=[
                                {
                                    "targetGroupArn": self.target_group_arn,
                                    "containerName": container_name,
                                    "containerPort": self.container_port,
                                }
                            ],
                        )

                        logger.info("Service updated after stabilization")
                        return update_response["service"]["serviceArn"]
                    except Exception as stabilize_error:
                        logger.error(
                            f"Failed to update service after stabilization: {str(stabilize_error)}"
                        )
                        # Don't return None - let it fall through to service deletion/recreation logic
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
                        update_response = self.ecs.update_service(
                            cluster=self.cluster_arn,
                            service=service_name,
                            taskDefinition=self.task_definition_arn,
                            desiredCount=1,
                            enableExecuteCommand=True,
                            loadBalancers=[
                                {
                                    "targetGroupArn": self.target_group_arn,
                                    "containerName": container_name,
                                    "containerPort": self.container_port,
                                }
                            ],
                        )
                        logger.info(
                            "Successfully updated service found via list_services"
                        )
                        return update_response["service"]["serviceArn"]
                    except Exception as list_update_error:
                        logger.error(
                            f"Failed to update service found via list: {str(list_update_error)}"
                        )
                        logger.error(f"List update error type: {type(list_update_error).__name__}")
                        if hasattr(list_update_error, 'response'):
                            logger.error(f"AWS error response: {list_update_error.response}")
            except Exception as list_error:
                logger.error(f"Failed to list services: {str(list_error)}")

        # If we get here, either no service exists or all update attempts failed
        # In case of failed updates, we should delete the problematic service and create a new one
        if service_exists:
            logger.warning("Service exists but cannot be updated. Attempting to delete and recreate...")
            try:
                # First, try to delete the existing service
                logger.info(f"Deleting problematic service: {service_name}")
                self.ecs.delete_service(
                    cluster=self.cluster_arn,
                    service=service_name,
                    force=True
                )
                
                # Wait a moment for deletion to process
                import time
                time.sleep(5)
                
                logger.info("Successfully deleted problematic service. Will create new one.")
                service_exists = False
                
            except Exception as delete_error:
                logger.error(f"Failed to delete problematic service: {str(delete_error)}")
                raise Exception(
                    f"Service exists but cannot be updated or deleted. Manual intervention required. Error: {str(delete_error)}"
                )

        logger.info(f"No existing service found. Creating new service: {service_name}")
        try:
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
                        "assignPublicIp": "ENABLED",
                    }
                },
                loadBalancers=[
                    {
                        "targetGroupArn": self.target_group_arn,
                        "containerName": getattr(self, "_existing_container_name", None)
                        or self.project_name,
                        "containerPort": self.container_port,
                    }
                ],
                tags=[{"key": "Name", "value": service_name}],
            )

            service_arn = response["service"]["serviceArn"]
            logger.info(f"ECS service created successfully: {service_arn}")
            logger.info(f"Returning service ARN: {service_arn}")
            return service_arn

        except Exception as create_error:
            logger.error(f"Service creation failed: {str(create_error)}")
            logger.error(f"Create error type: {type(create_error).__name__}")
            if hasattr(create_error, 'response'):
                logger.error(f"AWS error response: {create_error.response}")
                
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
                    update_response = self.ecs.update_service(
                        cluster=self.cluster_arn,
                        service=service_name,
                        taskDefinition=self.task_definition_arn,
                        desiredCount=1,
                        enableExecuteCommand=True,
                        loadBalancers=[
                            {
                                "targetGroupArn": self.target_group_arn,
                                "containerName": container_name,
                                "containerPort": self.container_port,
                            }
                        ],
                    )
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

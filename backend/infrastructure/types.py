from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from infrastructure.constants import (
    DEFAULT_LAUNCH_TYPE,
    DEFAULT_EC2_INSTANCE_TYPE,
    DEFAULT_EC2_MIN_SIZE,
    DEFAULT_EC2_MAX_SIZE,
    DEFAULT_EC2_DESIRED_CAPACITY,
    DEFAULT_EC2_USE_SPOT,
    DEFAULT_EC2_SPOT_MAX_PRICE,
    DEFAULT_EC2_KEY_NAME,
    DEFAULT_CAPACITY_PROVIDER_TARGET_CAPACITY,
    DEFAULT_CPU,
    DEFAULT_MEMORY,
    DEFAULT_DISK_SIZE,
)


class EnvironmentVariable(BaseModel):
    key: str
    value: Optional[str] = None
    is_secret: bool = Field(False, alias="isSecret")
    secret_key: Optional[str] = Field(None, alias="secretKey")

    class Config:
        populate_by_name = True


class ECSInfrastructureArgs(BaseModel):
    project_name: str = Field(alias="projectName")
    project_id: Optional[str] = Field(None, alias="projectId")
    image_uri: str = Field(alias="imageUri")
    container_port: int = Field(3000, alias="containerPort")
    health_check_path: str = Field("/", alias="healthCheckPath")
    region: str = "us-east-1"
    existing_vpc_id: Optional[str] = Field(None, alias="existingVpcId")
    existing_subnet_ids: Optional[List[str]] = Field(None, alias="existingSubnetIds")
    existing_cluster_arn: Optional[str] = Field(None, alias="existingClusterArn")
    environment_variables: List[EnvironmentVariable] = Field(
        default_factory=list, alias="environmentVariables"
    )
    cpu: int = DEFAULT_CPU
    memory: int = DEFAULT_MEMORY
    disk_size: int = Field(DEFAULT_DISK_SIZE, alias="diskSize")
    
    # ECS Launch Type Configuration
    launch_type: str = Field(DEFAULT_LAUNCH_TYPE, alias="launchType")
    ec2_instance_type: str = Field(DEFAULT_EC2_INSTANCE_TYPE, alias="ec2InstanceType")
    ec2_min_size: int = Field(DEFAULT_EC2_MIN_SIZE, alias="ec2MinSize")
    ec2_max_size: int = Field(DEFAULT_EC2_MAX_SIZE, alias="ec2MaxSize")
    ec2_desired_capacity: int = Field(DEFAULT_EC2_DESIRED_CAPACITY, alias="ec2DesiredCapacity")
    ec2_use_spot: bool = Field(DEFAULT_EC2_USE_SPOT, alias="ec2UseSpot")
    ec2_spot_max_price: Optional[str] = Field(DEFAULT_EC2_SPOT_MAX_PRICE, alias="ec2SpotMaxPrice")
    ec2_key_name: Optional[str] = Field(DEFAULT_EC2_KEY_NAME, alias="ec2KeyName")
    capacity_provider_target_capacity: int = Field(DEFAULT_CAPACITY_PROVIDER_TARGET_CAPACITY, alias="capacityProviderTargetCapacity")

    class Config:
        populate_by_name = True


class ECSInfrastructureOutput(BaseModel):
    cluster_arn: str = Field(alias="clusterArn")
    service_arn: str = Field(alias="serviceArn")
    load_balancer_arn: str = Field(alias="loadBalancerArn")
    load_balancer_dns: str = Field(alias="loadBalancerDns")
    load_balancer_name: str = Field(alias="loadBalancerName")
    vpc_id: Optional[str] = Field(None, alias="vpcId")
    subnet_ids: Optional[List[str]] = Field(None, alias="subnetIds")

    class Config:
        populate_by_name = True


class SecurityGroupIds(BaseModel):
    alb_security_group_id: str = Field(alias="albSecurityGroupId")
    ecs_security_group_id: str = Field(alias="ecsSecurityGroupId")

    class Config:
        populate_by_name = True

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EnvironmentVariable(BaseModel):
    key: str
    value: Optional[str] = None
    is_secret: bool = Field(False, alias="isSecret")
    secret_key: Optional[str] = Field(None, alias="secretKey")

    class Config:
        populate_by_name = True


class ECSInfrastructureArgs(BaseModel):
    project_name: str = Field(alias="projectName")
    image_uri: str = Field(alias="imageUri")
    container_port: int = Field(3000, alias="containerPort")
    health_check_path: str = Field("/health", alias="healthCheckPath")
    region: str = "us-east-1"
    existing_vpc_id: Optional[str] = Field(None, alias="existingVpcId")
    existing_subnet_ids: Optional[List[str]] = Field(None, alias="existingSubnetIds")
    existing_cluster_arn: Optional[str] = Field(None, alias="existingClusterArn")
    environment_variables: List[EnvironmentVariable] = Field(default_factory=list, alias="environmentVariables")
    cpu: int = 256
    memory: int = 512
    disk_size: int = Field(21, alias="diskSize")

    class Config:
        populate_by_name = True


class ECSInfrastructureOutput(BaseModel):
    cluster_arn: str = Field(alias="clusterArn")
    service_arn: str = Field(alias="serviceArn")
    load_balancer_arn: str = Field(alias="loadBalancerArn")
    load_balancer_dns: str = Field(alias="loadBalancerDns")

    class Config:
        populate_by_name = True


class SecurityGroupIds(BaseModel):
    alb_security_group_id: str = Field(alias="albSecurityGroupId")
    ecs_security_group_id: str = Field(alias="ecsSecurityGroupId")

    class Config:
        populate_by_name = True
import boto3
from typing import List, Optional, Tuple
import logging

from ..types import EnvironmentVariable, SecurityGroupIds

logger = logging.getLogger(__name__)


class VPCService:
    def __init__(
        self,
        project_name: str,
        environment_variables: List[EnvironmentVariable],
        region: str = "us-east-1",
        existing_vpc_id: Optional[str] = None,
        existing_subnet_ids: Optional[List[str]] = None,
        aws_credentials: Optional[dict] = None
    ):
        self.project_name = project_name
        self.environment_variables = environment_variables
        self.region = region
        self.existing_vpc_id = existing_vpc_id
        self.existing_subnet_ids = existing_subnet_ids
        self.aws_credentials = aws_credentials
        
        # Initialize EC2 client with custom credentials if provided
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update({
                "aws_access_key_id": aws_credentials["access_key"],
                "aws_secret_access_key": aws_credentials["secret_key"]
            })
        
        self.ec2 = boto3.client("ec2", **client_config)
        
        self.vpc_id: str = ""
        self.subnet_ids: List[str] = []
        self.security_group_ids: SecurityGroupIds = None
    
    async def initialize(self):
        """Initialize VPC resources"""
        if self.existing_vpc_id and self.existing_subnet_ids:
            logger.info(f"Using existing VPC: {self.existing_vpc_id}")
            self.vpc_id = self.existing_vpc_id
            self.subnet_ids = self.existing_subnet_ids
        else:
            # Get default VPC
            self.vpc_id = await self._get_default_vpc()
            # Get subnets
            self.subnet_ids = await self._get_vpc_subnets()
        
        # Create security groups
        self.security_group_ids = await self._create_security_groups()
    
    async def _get_default_vpc(self) -> str:
        """Get the default VPC"""
        response = self.ec2.describe_vpcs(
            Filters=[{"Name": "is-default", "Values": ["true"]}]
        )
        
        if not response["Vpcs"]:
            raise Exception("No default VPC found")
        
        vpc_id = response["Vpcs"][0]["VpcId"]
        logger.info(f"Using default VPC: {vpc_id}")
        return vpc_id
    
    async def _get_vpc_subnets(self) -> List[str]:
        """Get subnets for the VPC"""
        response = self.ec2.describe_subnets(
            Filters=[
                {"Name": "vpc-id", "Values": [self.vpc_id]},
                {"Name": "default-for-az", "Values": ["true"]}
            ]
        )
        
        subnet_ids = [subnet["SubnetId"] for subnet in response["Subnets"]]
        
        # If no default subnets, get any available subnets
        if not subnet_ids:
            response = self.ec2.describe_subnets(
                Filters=[{"Name": "vpc-id", "Values": [self.vpc_id]}]
            )
            subnet_ids = [subnet["SubnetId"] for subnet in response["Subnets"][:2]]
        
        if len(subnet_ids) < 2:
            raise Exception("Need at least 2 subnets for ALB")
        
        logger.info(f"Using subnets: {subnet_ids}")
        return subnet_ids
    
    async def _create_security_groups(self) -> SecurityGroupIds:
        """Create or update security groups"""
        alb_sg_id = await self._create_alb_security_group()
        ecs_sg_id = await self._create_ecs_security_group(alb_sg_id)
        
        return SecurityGroupIds(
            alb_security_group_id=alb_sg_id,
            ecs_security_group_id=ecs_sg_id
        )
    
    async def _create_alb_security_group(self) -> str:
        """Create ALB security group"""
        sg_name = f"{self.project_name}-alb-sg"
        
        try:
            # Check if security group exists
            response = self.ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [self.vpc_id]}
                ]
            )
            
            if response["SecurityGroups"]:
                sg_id = response["SecurityGroups"][0]["GroupId"]
                logger.info(f"Found existing ALB security group: {sg_id}")
                return sg_id
        except Exception:
            pass
        
        # Create new security group
        response = self.ec2.create_security_group(
            GroupName=sg_name,
            Description=f"Security group for {self.project_name} ALB",
            VpcId=self.vpc_id,
            TagSpecifications=[{
                "ResourceType": "security-group",
                "Tags": [{"Key": "Name", "Value": sg_name}]
            }]
        )
        
        sg_id = response["GroupId"]
        
        # Add ingress rules
        self.ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                }
            ]
        )
        
        logger.info(f"Created ALB security group: {sg_id}")
        return sg_id
    
    async def _create_ecs_security_group(self, alb_sg_id: str) -> str:
        """Create ECS security group"""
        sg_name = f"{self.project_name}-ecs-sg"
        
        try:
            # Check if security group exists
            response = self.ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [self.vpc_id]}
                ]
            )
            
            if response["SecurityGroups"]:
                sg_id = response["SecurityGroups"][0]["GroupId"]
                logger.info(f"Found existing ECS security group: {sg_id}")
                return sg_id
        except Exception:
            pass
        
        # Create new security group
        response = self.ec2.create_security_group(
            GroupName=sg_name,
            Description=f"Security group for {self.project_name} ECS tasks",
            VpcId=self.vpc_id,
            TagSpecifications=[{
                "ResourceType": "security-group",
                "Tags": [{"Key": "Name", "Value": sg_name}]
            }]
        )
        
        sg_id = response["GroupId"]
        
        # Add ingress rule from ALB
        self.ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 1,
                "ToPort": 65535,
                "UserIdGroupPairs": [{"GroupId": alb_sg_id}]
            }]
        )
        
        logger.info(f"Created ECS security group: {sg_id}")
        return sg_id
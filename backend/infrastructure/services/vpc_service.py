from typing import List, Optional
import logging

from utils.aws_client import create_client
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
        aws_credentials: Optional[dict] = None,
    ):
        self.project_name = project_name
        self.environment_variables = environment_variables
        self.region = region
        self.existing_vpc_id = existing_vpc_id
        self.existing_subnet_ids = existing_subnet_ids
        self.aws_credentials = aws_credentials

        # Initialize EC2 client with custom credentials if provided
        self.ec2 = create_client("ec2", region, aws_credentials)

        self.vpc_id: str = ""
        self.subnet_ids: List[str] = []
        self.security_group_ids: SecurityGroupIds = None

    async def initialize(self):
        """Initialize VPC resources"""
        logger.info(f"🔍 VPC Service Initialize - existing_vpc_id: '{self.existing_vpc_id}', existing_subnet_ids: {self.existing_subnet_ids}")
        if self.existing_vpc_id:
            logger.info(f"Using existing VPC: {self.existing_vpc_id}")
            self.vpc_id = self.existing_vpc_id
            
            if self.existing_subnet_ids:
                # Use provided subnets
                logger.info(f"Using existing subnets: {self.existing_subnet_ids}")
                self.subnet_ids = self.existing_subnet_ids
            else:
                # Create subnets in the existing VPC
                logger.info(f"Creating subnets in existing VPC: {self.existing_vpc_id}")
                self.subnet_ids = await self._create_subnets()
        else:
            # Create new VPC and subnets for this project
            logger.info(f"Creating new VPC for project: {self.project_name}")
            self.vpc_id = await self._create_vpc()
            self.subnet_ids = await self._create_subnets()

        # Create security groups
        self.security_group_ids = await self._create_security_groups()

    async def _create_vpc(self) -> str:
        """Create a new VPC for the project"""
        vpc_name = f"{self.project_name}-vpc"

        # First check if a VPC with this name already exists
        try:
            response = self.ec2.describe_vpcs(
                Filters=[
                    {"Name": "tag:Name", "Values": [vpc_name]},
                    {"Name": "tag:Project", "Values": [self.project_name]},
                    {"Name": "state", "Values": ["available"]}
                ]
            )
            
            if response["Vpcs"]:
                # Use the existing VPC
                vpc_id = response["Vpcs"][0]["VpcId"]
                logger.info(f"Found existing VPC with name {vpc_name}: {vpc_id}")
                
                # Ensure DNS support is enabled on the existing VPC
                self.ec2.modify_vpc_attribute(
                    VpcId=vpc_id, EnableDnsSupport={"Value": True}
                )
                self.ec2.modify_vpc_attribute(
                    VpcId=vpc_id, EnableDnsHostnames={"Value": True}
                )
                
                return vpc_id
        except Exception as e:
            logger.warning(f"Error checking for existing VPC: {e}")

        # Create VPC if it doesn't exist
        response = self.ec2.create_vpc(
            CidrBlock="10.0.0.0/16",
            TagSpecifications=[
                {
                    "ResourceType": "vpc",
                    "Tags": [
                        {"Key": "Name", "Value": vpc_name},
                        {"Key": "Project", "Value": self.project_name},
                    ],
                }
            ],
        )

        vpc_id = response["Vpc"]["VpcId"]
        logger.info(f"Created new VPC: {vpc_id}")

        # Wait for VPC to be available
        waiter = self.ec2.get_waiter("vpc_available")
        waiter.wait(VpcIds=[vpc_id])

        # Enable DNS hostnames and resolution
        self.ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
        self.ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

        # Create and attach internet gateway
        igw_response = self.ec2.create_internet_gateway(
            TagSpecifications=[
                {
                    "ResourceType": "internet-gateway",
                    "Tags": [
                        {"Key": "Name", "Value": f"{self.project_name}-igw"},
                        {"Key": "Project", "Value": self.project_name},
                    ],
                }
            ]
        )
        igw_id = igw_response["InternetGateway"]["InternetGatewayId"]

        self.ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        logger.info(f"Created and attached Internet Gateway: {igw_id}")

        return vpc_id

    async def _create_subnets(self) -> List[str]:
        """Create subnets for the VPC"""
        # First check if subnets already exist for this VPC
        try:
            response = self.ec2.describe_subnets(
                Filters=[
                    {"Name": "vpc-id", "Values": [self.vpc_id]},
                    {"Name": "tag:Project", "Values": [self.project_name]},
                    {"Name": "state", "Values": ["available"]}
                ]
            )
            
            if response["Subnets"] and len(response["Subnets"]) >= 2:
                # Use existing subnets
                subnet_ids = [subnet["SubnetId"] for subnet in response["Subnets"][:2]]
                logger.info(f"Found existing subnets for project {self.project_name}: {subnet_ids}")
                
                # Ensure public IP assignment is enabled
                for subnet_id in subnet_ids:
                    self.ec2.modify_subnet_attribute(
                        SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True}
                    )
                
                return subnet_ids
        except Exception as e:
            logger.warning(f"Error checking for existing subnets: {e}")

        # Get available AZs
        azs_response = self.ec2.describe_availability_zones()
        azs = [az["ZoneName"] for az in azs_response["AvailabilityZones"]][
            :2
        ]  # Use first 2 AZs

        if len(azs) < 2:
            raise Exception("Need at least 2 availability zones")

        subnet_ids = []
        cidr_blocks = ["10.0.1.0/24", "10.0.2.0/24"]

        for i, az in enumerate(azs):
            subnet_name = f"{self.project_name}-subnet-{i+1}"

            response = self.ec2.create_subnet(
                VpcId=self.vpc_id,
                CidrBlock=cidr_blocks[i],
                AvailabilityZone=az,
                TagSpecifications=[
                    {
                        "ResourceType": "subnet",
                        "Tags": [
                            {"Key": "Name", "Value": subnet_name},
                            {"Key": "Project", "Value": self.project_name},
                        ],
                    }
                ],
            )

            subnet_id = response["Subnet"]["SubnetId"]
            subnet_ids.append(subnet_id)

            # Enable public IP assignment
            self.ec2.modify_subnet_attribute(
                SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True}
            )

            logger.info(f"Created subnet: {subnet_id} in AZ: {az}")

        # Create route table and add route to internet gateway
        await self._create_route_table(subnet_ids)

        return subnet_ids

    async def _create_route_table(self, subnet_ids: List[str]):
        """Create route table and associate with subnets"""
        rt_name = f"{self.project_name}-rt"

        # Create route table
        response = self.ec2.create_route_table(
            VpcId=self.vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "route-table",
                    "Tags": [
                        {"Key": "Name", "Value": rt_name},
                        {"Key": "Project", "Value": self.project_name},
                    ],
                }
            ],
        )

        rt_id = response["RouteTable"]["RouteTableId"]

        # Get internet gateway for this VPC
        igw_response = self.ec2.describe_internet_gateways(
            Filters=[{"Name": "attachment.vpc-id", "Values": [self.vpc_id]}]
        )
        igw_id = igw_response["InternetGateways"][0]["InternetGatewayId"]

        # Add route to internet gateway
        self.ec2.create_route(
            RouteTableId=rt_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id
        )

        # Associate route table with subnets
        for subnet_id in subnet_ids:
            self.ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)

        logger.info(f"Created route table: {rt_id} and associated with subnets")

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
                {"Name": "default-for-az", "Values": ["true"]},
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
            alb_security_group_id=alb_sg_id, ecs_security_group_id=ecs_sg_id
        )

    async def _create_alb_security_group(self) -> str:
        """Create ALB security group"""
        sg_name = f"{self.project_name}-alb-sg"

        try:
            # Check if security group exists
            response = self.ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [self.vpc_id]},
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
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": sg_name}],
                }
            ],
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
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
            ],
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
                    {"Name": "vpc-id", "Values": [self.vpc_id]},
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
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": sg_name}],
                }
            ],
        )

        sg_id = response["GroupId"]

        # Add ingress rule from ALB
        self.ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 1,
                    "ToPort": 65535,
                    "UserIdGroupPairs": [{"GroupId": alb_sg_id}],
                }
            ],
        )

        logger.info(f"Created ECS security group: {sg_id}")
        return sg_id

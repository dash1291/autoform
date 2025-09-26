"""
Simple integration test for VPC Service using moto
"""
import pytest_asyncio
from infrastructure.services.vpc_service import VPCService
from infrastructure.types import EnvironmentVariable


class TestSimpleVPCService:
    """Simple test for VPC Service functionality"""

    @pytest_asyncio.fixture
    async def vpc_service(
        self, test_project_config, test_region, aws_credentials, mock_aws_services
    ):
        """Create VPC service instance for testing"""
        env_vars = [
            EnvironmentVariable(key="NODE_ENV", value="production"),
            EnvironmentVariable(key="PORT", value="3000"),
        ]

        service = VPCService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            region=test_region,
            aws_credentials=aws_credentials,
        )
        yield service

    async def test_vpc_initialization(self, vpc_service, ec2_client):
        """Test VPC initialization creates all necessary resources"""
        # Initialize VPC infrastructure
        await vpc_service.initialize()

        # Verify VPC was created
        assert hasattr(vpc_service, "vpc_id")
        assert vpc_service.vpc_id is not None
        assert vpc_service.vpc_id.startswith("vpc-")

        # Verify subnets were created
        assert hasattr(vpc_service, "subnet_ids")
        assert vpc_service.subnet_ids is not None
        assert len(vpc_service.subnet_ids) > 0

        # Verify security groups were created
        assert hasattr(vpc_service, "security_group_ids")
        assert vpc_service.security_group_ids is not None

        # Verify VPC exists in AWS (mocked)
        vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_service.vpc_id])
        assert len(vpcs["Vpcs"]) == 1

        vpc = vpcs["Vpcs"][0]
        assert vpc["CidrBlock"] == "10.0.0.0/16"
        assert vpc["State"] == "available"

    async def test_vpc_with_existing_vpc_id(
        self, test_project_config, test_region, aws_credentials, mock_aws_services
    ):
        """Test VPC service when existing VPC ID is provided"""
        # Create a VPC first
        from tests.conftest import get_aws_client

        ec2_client = get_aws_client("ec2", test_region)

        # Create VPC
        vpc_response = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
        existing_vpc_id = vpc_response["Vpc"]["VpcId"]

        # Create subnet
        subnet_response = ec2_client.create_subnet(
            VpcId=existing_vpc_id, CidrBlock="10.0.1.0/24"
        )
        existing_subnet_id = subnet_response["Subnet"]["SubnetId"]

        # Create VPC service with existing resources
        env_vars = [EnvironmentVariable(key="NODE_ENV", value="production")]

        service = VPCService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            region=test_region,
            existing_vpc_id=existing_vpc_id,
            existing_subnet_ids=[existing_subnet_id],
            aws_credentials=aws_credentials,
        )

        # Initialize - should use existing resources
        await service.initialize()

        # Verify it used the existing VPC
        assert service.vpc_id == existing_vpc_id
        assert existing_subnet_id in service.subnet_ids

"""
Working integration tests for infrastructure services
Tests only the functionality that works reliably with moto
"""
import pytest
import pytest_asyncio
from infrastructure.services.vpc_service import VPCService
from infrastructure.services.ecs_service import ECSService
from infrastructure.services.iam_service import IAMService
from infrastructure.types import EnvironmentVariable


class TestWorkingVPCService:
    """Test VPC Service functionality that works with moto"""
    
    @pytest_asyncio.fixture
    async def vpc_service(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        """Create VPC service instance for testing"""
        env_vars = [
            EnvironmentVariable(key="NODE_ENV", value="production"),
            EnvironmentVariable(key="PORT", value="3000")
        ]
        
        service = VPCService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            region=test_region,
            aws_credentials=aws_credentials
        )
        yield service
    
    async def test_vpc_service_initialization(self, vpc_service, ec2_client):
        """Test VPC service creates all necessary infrastructure"""
        # Initialize VPC infrastructure
        await vpc_service.initialize()
        
        # Verify VPC components are created
        assert hasattr(vpc_service, 'vpc_id')
        assert hasattr(vpc_service, 'subnet_ids') 
        assert hasattr(vpc_service, 'security_group_ids')
        
        assert vpc_service.vpc_id is not None
        assert vpc_service.subnet_ids is not None
        assert len(vpc_service.subnet_ids) > 0
        assert vpc_service.security_group_ids is not None
        
        # Verify VPC exists in AWS (mocked)
        vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_service.vpc_id])
        assert len(vpcs["Vpcs"]) == 1
        
        vpc = vpcs["Vpcs"][0]
        assert vpc["CidrBlock"] == "10.0.0.0/16"
        assert vpc["State"] == "available"
        
        # Verify subnets exist
        if vpc_service.subnet_ids:
            subnets = ec2_client.describe_subnets(SubnetIds=vpc_service.subnet_ids)
            assert len(subnets["Subnets"]) == len(vpc_service.subnet_ids)
            
            for subnet in subnets["Subnets"]:
                assert subnet["VpcId"] == vpc_service.vpc_id
                assert subnet["State"] == "available"
    
    async def test_vpc_with_existing_resources(self, test_project_config, test_region, aws_credentials, mock_aws_services, ec2_client):
        """Test VPC service when existing resources are provided"""
        # Create existing VPC and subnet
        vpc_response = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
        existing_vpc_id = vpc_response["Vpc"]["VpcId"]
        
        subnet_response = ec2_client.create_subnet(
            VpcId=existing_vpc_id,
            CidrBlock="10.0.1.0/24"
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
            aws_credentials=aws_credentials
        )
        
        # Initialize - should use existing resources
        await service.initialize()
        
        # Verify it used the existing VPC
        assert service.vpc_id == existing_vpc_id
        assert existing_subnet_id in service.subnet_ids


class TestWorkingECSService:
    """Test ECS Service functionality that works with moto"""
    
    @pytest_asyncio.fixture
    async def ecs_service(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        """Create ECS service instance for testing"""
        env_vars = [
            EnvironmentVariable(key="NODE_ENV", value="production"),
            EnvironmentVariable(key="PORT", value="3000")
        ]
        
        service = ECSService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            cpu=test_project_config["cpu"],
            memory=test_project_config["memory"],
            disk_size=test_project_config["disk_size"],
            image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/test-project:latest",
            container_port=test_project_config["port"],
            region=test_region,
            vpc_id="vpc-12345",
            subnet_ids=["subnet-12345", "subnet-67890"],
            security_group_id="sg-12345",
            aws_credentials=aws_credentials
        )
        yield service
    
    async def test_ecs_service_initialization(self, ecs_service, ecs_client):
        """Test ECS service creates cluster and task definition"""
        # Initialize ECS infrastructure
        await ecs_service.initialize()
        
        # Verify ECS components are created
        assert hasattr(ecs_service, 'cluster_arn')
        assert hasattr(ecs_service, 'task_definition_arn')
        
        assert ecs_service.cluster_arn is not None
        assert ecs_service.task_definition_arn is not None
        
        # Verify cluster exists
        cluster_name = f"{ecs_service.project_name}-cluster"
        clusters = ecs_client.describe_clusters(clusters=[cluster_name])
        assert len(clusters["clusters"]) == 1
        
        cluster = clusters["clusters"][0]
        assert cluster["clusterName"] == cluster_name
        assert cluster["status"] == "ACTIVE"
        
        # Verify task definition exists
        task_def_family = f"{ecs_service.project_name}-task"
        task_defs = ecs_client.describe_task_definition(taskDefinition=task_def_family)
        
        task_def = task_defs["taskDefinition"]
        assert task_def["family"] == task_def_family
        assert task_def["cpu"] == str(ecs_service.cpu)
        assert task_def["memory"] == str(ecs_service.memory)


class TestWorkingIAMService:
    """Test IAM Service functionality that works with moto"""
    
    @pytest_asyncio.fixture
    async def iam_service(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        """Create IAM service instance for testing"""
        service = IAMService(
            project_name=test_project_config["project_name"],
            region=test_region,
            aws_credentials=aws_credentials
        )
        yield service
    
    async def test_iam_service_initialization(self, iam_service, iam_client):
        """Test IAM service creates all necessary roles"""
        # Initialize IAM roles
        await iam_service.initialize()
        
        # Verify IAM roles are created
        assert hasattr(iam_service, 'execution_role_arn')
        assert hasattr(iam_service, 'task_role_arn') 
        assert hasattr(iam_service, 'codebuild_role_arn')
        
        assert iam_service.execution_role_arn is not None
        assert iam_service.task_role_arn is not None
        assert iam_service.codebuild_role_arn is not None
        
        # Verify ARN format
        assert "arn:aws:iam::" in iam_service.execution_role_arn
        assert "arn:aws:iam::" in iam_service.task_role_arn
        assert "arn:aws:iam::" in iam_service.codebuild_role_arn
        
        # Verify roles exist in IAM
        execution_role_name = f"{iam_service.project_name}-ecs-execution-role"
        task_role_name = f"{iam_service.project_name}-ecs-task-role"
        codebuild_role_name = f"{iam_service.project_name}-codebuild-role"
        
        # Check execution role
        execution_role = iam_client.get_role(RoleName=execution_role_name)["Role"]
        assert execution_role["RoleName"] == execution_role_name
        
        # Check task role  
        task_role = iam_client.get_role(RoleName=task_role_name)["Role"]
        assert task_role["RoleName"] == task_role_name
        
        # Check codebuild role
        codebuild_role = iam_client.get_role(RoleName=codebuild_role_name)["Role"]
        assert codebuild_role["RoleName"] == codebuild_role_name


class TestServiceIntegration:
    """Test integration between services"""
    
    async def test_vpc_to_ecs_integration(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        """Test VPC service providing resources to ECS service"""
        env_vars = [
            EnvironmentVariable(key="NODE_ENV", value="production"),
            EnvironmentVariable(key="PORT", value="3000")
        ]
        
        # 1. Initialize VPC infrastructure
        vpc_service = VPCService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            region=test_region,
            aws_credentials=aws_credentials
        )
        await vpc_service.initialize()
        
        # 2. Initialize ECS service using VPC resources
        ecs_service = ECSService(
            project_name=test_project_config["project_name"],
            environment_variables=env_vars,
            cpu=test_project_config["cpu"],
            memory=test_project_config["memory"],
            disk_size=test_project_config["disk_size"],
            image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/test-project:latest",
            container_port=test_project_config["port"],
            region=test_region,
            vpc_id=vpc_service.vpc_id,
            subnet_ids=vpc_service.subnet_ids,
            security_group_id=vpc_service.security_group_ids.ecs_security_group_id,
            aws_credentials=aws_credentials
        )
        await ecs_service.initialize()
        
        # Verify integration
        assert ecs_service.vpc_id == vpc_service.vpc_id
        assert set(ecs_service.subnet_ids) == set(vpc_service.subnet_ids)
        assert ecs_service.security_group_id == vpc_service.security_group_ids.ecs_security_group_id
        
        # Verify both services created their resources
        assert vpc_service.vpc_id is not None
        assert ecs_service.cluster_arn is not None
        assert ecs_service.task_definition_arn is not None
    
    async def test_iam_to_ecs_integration(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        """Test IAM service providing roles to ECS service"""
        # 1. Initialize IAM roles
        iam_service = IAMService(
            project_name=test_project_config["project_name"],
            region=test_region,
            aws_credentials=aws_credentials
        )
        await iam_service.initialize()
        
        # 2. Verify roles are created and have correct ARN format
        assert iam_service.execution_role_arn is not None
        assert iam_service.task_role_arn is not None
        assert iam_service.codebuild_role_arn is not None
        
        # These roles would be used by ECS service for task execution
        # In a real deployment, the ECS service would reference these ARNs
        assert f"{iam_service.project_name}-ecs-execution-role" in iam_service.execution_role_arn
        assert f"{iam_service.project_name}-ecs-task-role" in iam_service.task_role_arn
        assert f"{iam_service.project_name}-codebuild-role" in iam_service.codebuild_role_arn
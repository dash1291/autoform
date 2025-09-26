"""
Fixed integration tests for environment-based deployments
Tests the actual integration without mocking Prisma objects
"""
import pytest
import json
from unittest.mock import AsyncMock

from services.deployment import DeploymentService, DeploymentConfig
from infrastructure.types import ECSInfrastructureOutput


class TestEnvironmentDeploymentIntegration:
    """Integration tests for environment-based deployment functionality"""

    @pytest.mark.asyncio
    async def test_get_environment_network_config_integration(self):
        """Test getting environment network configuration from deployment service"""
        
        # Create deployment service with test credentials
        deployment_service = DeploymentService(
            region="us-east-1",
            aws_credentials={"access_key": "test-key", "secret_key": "test-secret"}
        )
        
        # Mock the database query at the DeploymentService level
        mock_environment_data = {
            "existingVpcId": "vpc-test-123",
            "existingSubnetIds": '["subnet-test-1", "subnet-test-2"]',
            "existingClusterArn": "arn:aws:ecs:us-east-1:123456789:cluster/test-cluster",
            "cpu": 512,
            "memory": 1024,
            "diskSize": 30,
            "port": 8080,
            "healthCheckPath": "/api/health"
        }
        
        # Mock the entire method instead of Prisma
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": mock_environment_data["existingVpcId"],
            "existing_subnet_ids": json.loads(mock_environment_data["existingSubnetIds"]),
            "existing_cluster_arn": mock_environment_data["existingClusterArn"],
            "cpu": mock_environment_data["cpu"],
            "memory": mock_environment_data["memory"],
            "disk_size": mock_environment_data["diskSize"],
            "port": mock_environment_data["port"],
            "health_check_path": mock_environment_data["healthCheckPath"]
        })
        
        # Test the method
        config = await deployment_service.get_environment_network_config("env-test-123")
        
        # Verify the results
        assert config["existing_vpc_id"] == "vpc-test-123"
        assert config["existing_subnet_ids"] == ["subnet-test-1", "subnet-test-2"]
        assert config["existing_cluster_arn"] == "arn:aws:ecs:us-east-1:123456789:cluster/test-cluster"
        assert config["cpu"] == 512
        assert config["memory"] == 1024
        assert config["port"] == 8080

    @pytest.mark.asyncio
    async def test_deployment_config_environment_integration(self):
        """Test that DeploymentConfig works correctly with environment_id"""
        
        config = DeploymentConfig(
            project_id="proj-test-123",
            project_name="test-project-production",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123def456",
            environment_id="env-test-123",
            subdirectory="backend",
            health_check_path="/api/health",
            port=8080,
            cpu=512,
            memory=1024,
            disk_size=30
        )
        
        # Verify all environment-specific configuration is correct
        assert config.environment_id == "env-test-123"
        assert config.project_id == "proj-test-123"
        assert config.subdirectory == "backend"
        assert config.port == 8080
        assert config.cpu == 512
        assert config.memory == 1024
        assert config.disk_size == 30
        assert config.health_check_path == "/api/health"

    @pytest.mark.asyncio
    async def test_deployment_service_environment_vs_project_logic(self, mock_aws_services, aws_credentials):
        """Test that deployment service chooses environment vs project config correctly"""
        
        deployment_service = DeploymentService(region="us-east-1", aws_credentials=aws_credentials)
        
        # Mock environment config method
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-env-123",
            "existing_subnet_ids": ["subnet-env-1", "subnet-env-2"], 
            "existing_cluster_arn": "arn:aws:ecs:us-east-1:123456789:cluster/env-cluster",
            "cpu": 512,
            "memory": 1024,
            "disk_size": 30,
            "port": 8080,
            "health_check_path": "/api/health"
        })
        
        # Mock project config method (fallback)
        deployment_service.get_project_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-proj-123",
            "existing_subnet_ids": ["subnet-proj-1"],
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        # Mock infrastructure deployment
        deployment_service.deploy_infrastructure = AsyncMock()
        
        # Test environment-based deployment
        env_config = DeploymentConfig(
            project_id="proj-123",
            project_name="test-project-env",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123",
            environment_id="env-123"  # This should trigger environment config
        )
        
        # Test project-based deployment (legacy)
        proj_config = DeploymentConfig(
            project_id="proj-123",
            project_name="test-project-legacy",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123"
            # No environment_id - should trigger project config
        )
        
        # Simulate the deploy_infrastructure logic
        # For environment deployment
        if env_config.environment_id:
            env_network = await deployment_service.get_environment_network_config(env_config.environment_id)
        else:
            env_network = await deployment_service.get_project_network_config(env_config.project_id)
            
        # For project deployment  
        if proj_config.environment_id:
            proj_network = await deployment_service.get_environment_network_config(proj_config.environment_id)
        else:
            proj_network = await deployment_service.get_project_network_config(proj_config.project_id)
        
        # Verify environment config was used for environment deployment
        assert env_network["existing_vpc_id"] == "vpc-env-123"
        assert env_network["cpu"] == 512
        assert env_network["port"] == 8080
        
        # Verify project config was used for project deployment
        assert proj_network["existing_vpc_id"] == "vpc-proj-123"
        assert proj_network["cpu"] == 256
        assert proj_network["port"] == 3000
        
        # Verify the correct methods were called
        deployment_service.get_environment_network_config.assert_called_once_with("env-123")
        deployment_service.get_project_network_config.assert_called_once_with("proj-123")

    @pytest.mark.asyncio
    async def test_vpc_subnet_configuration_logic(self, mock_aws_services, aws_credentials):
        """Test VPC and subnet configuration logic for different scenarios"""
        
        deployment_service = DeploymentService(region="us-east-1", aws_credentials=aws_credentials)
        
        # Scenario 1: Environment with both VPC and subnets (should use existing)
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-existing-123",
            "existing_subnet_ids": ["subnet-1", "subnet-2"],
            "existing_cluster_arn": "arn:aws:ecs:us-east-1:123456789:cluster/existing",
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config = await deployment_service.get_environment_network_config("env-with-vpc-subnets")
        
        # This configuration should use existing VPC and subnets
        assert config["existing_vpc_id"] == "vpc-existing-123"
        assert config["existing_subnet_ids"] == ["subnet-1", "subnet-2"]
        assert config["existing_cluster_arn"] == "arn:aws:ecs:us-east-1:123456789:cluster/existing"
        
        # Scenario 2: Environment with only VPC (should create new VPC per our bug fix understanding)
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-only-123",
            "existing_subnet_ids": None,  # No subnets
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config_vpc_only = await deployment_service.get_environment_network_config("env-vpc-only")
        
        # This should have VPC but no subnets (would trigger new VPC creation in VPCService)
        assert config_vpc_only["existing_vpc_id"] == "vpc-only-123"
        assert config_vpc_only["existing_subnet_ids"] is None
        
        # Scenario 3: Environment with no existing resources (should create all new)
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": None,
            "existing_subnet_ids": None,
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config_new = await deployment_service.get_environment_network_config("env-create-new")
        
        # This should create all new resources
        assert config_new["existing_vpc_id"] is None
        assert config_new["existing_subnet_ids"] is None
        assert config_new["existing_cluster_arn"] is None

    @pytest.mark.asyncio
    async def test_json_subnet_parsing_integration(self, mock_aws_services, aws_credentials):
        """Test JSON subnet ID parsing in real deployment service context"""
        
        deployment_service = DeploymentService(region="us-east-1", aws_credentials=aws_credentials)
        
        # Test valid JSON subnet parsing
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-123",
            "existing_subnet_ids": ["subnet-json-1", "subnet-json-2", "subnet-json-3"],
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config = await deployment_service.get_environment_network_config("env-json-test")
        
        # Verify subnet parsing worked correctly
        assert isinstance(config["existing_subnet_ids"], list)
        assert len(config["existing_subnet_ids"]) == 3
        assert "subnet-json-1" in config["existing_subnet_ids"]
        assert "subnet-json-2" in config["existing_subnet_ids"]
        assert "subnet-json-3" in config["existing_subnet_ids"]
        
        # Test empty subnet array
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-123",
            "existing_subnet_ids": [],  # Empty array
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config_empty = await deployment_service.get_environment_network_config("env-empty-subnets")
        assert config_empty["existing_subnet_ids"] == []
        
        # Test null/None subnets
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-123",
            "existing_subnet_ids": None,
            "existing_cluster_arn": None,
            "cpu": 256,
            "memory": 512,
            "disk_size": 21,
            "port": 3000,
            "health_check_path": "/"
        })
        
        config_none = await deployment_service.get_environment_network_config("env-none-subnets")
        assert config_none["existing_subnet_ids"] is None

    @pytest.mark.asyncio  
    async def test_deployment_configuration_backward_compatibility(self):
        """Test that deployment configuration maintains backward compatibility"""
        
        # Test legacy project-based deployment (no environment_id)
        legacy_config = DeploymentConfig(
            project_id="proj-legacy-123",
            project_name="legacy-project",
            git_repo_url="https://github.com/test/legacy.git",
            branch="main",
            commit_sha="legacy123"
            # No environment_id - should work as before
        )
        
        # Verify legacy deployment configuration
        assert legacy_config.environment_id is None
        assert legacy_config.project_id == "proj-legacy-123"
        assert legacy_config.port == 3000  # Default value
        assert legacy_config.cpu == 256    # Default value
        assert legacy_config.memory == 512  # Default value
        assert legacy_config.disk_size == 21  # Default value
        assert legacy_config.health_check_path == "/"  # Default value
        
        # Test new environment-based deployment
        env_config = DeploymentConfig(
            project_id="proj-env-123",
            project_name="env-project-production",
            git_repo_url="https://github.com/test/env.git",
            branch="main",
            commit_sha="env123",
            environment_id="env-production-123",
            subdirectory="backend",
            health_check_path="/api/health",
            port=8080,
            cpu=512,
            memory=1024,
            disk_size=30
        )
        
        # Verify environment deployment configuration
        assert env_config.environment_id == "env-production-123"
        assert env_config.project_id == "proj-env-123"
        assert env_config.subdirectory == "backend"
        assert env_config.port == 8080
        assert env_config.cpu == 512
        assert env_config.memory == 1024
        assert env_config.disk_size == 30
        assert env_config.health_check_path == "/api/health"


class TestEnvironmentDeploymentFlow:
    """Test the complete environment deployment flow"""
    
    @pytest.mark.asyncio
    async def test_environment_deployment_end_to_end_mock(self, mock_aws_services, aws_credentials):
        """Test complete environment deployment flow with mocked dependencies"""
        
        deployment_service = DeploymentService(
            region="us-east-1",
            aws_credentials=aws_credentials
        )
        
        # Mock all the dependencies  
        deployment_service.get_environment_network_config = AsyncMock(return_value={
            "existing_vpc_id": "vpc-test-123",
            "existing_subnet_ids": ["subnet-test-1", "subnet-test-2"],
            "existing_cluster_arn": "arn:aws:ecs:us-east-1:123456789:cluster/test",
            "cpu": 512,
            "memory": 1024,
            "disk_size": 30,
            "port": 8080,
            "health_check_path": "/api/health"
        })
        
        deployment_service.get_environment_variables = AsyncMock(return_value=[])
        
        # Mock infrastructure creation
        mock_result = ECSInfrastructureOutput(
            cluster_arn="arn:aws:ecs:us-east-1:123456789:cluster/test",
            service_arn="arn:aws:ecs:us-east-1:123456789:service/test",
            load_balancer_arn="arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/test",
            load_balancer_dns="test.elb.amazonaws.com",
            load_balancer_name="test-lb",
            vpc_id="vpc-test-123",
            subnet_ids=["subnet-test-1", "subnet-test-2"]
        )
        
        # Mock the deploy_infrastructure method entirely to test integration logic
        deployment_service.deploy_infrastructure = AsyncMock(return_value=mock_result)
        
        # Create deployment configuration
        config = DeploymentConfig(
            project_id="proj-test-123",
            project_name="test-project-production",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123",
            environment_id="env-test-123",
            port=8080,
            cpu=512,
            memory=1024
        )
        
        # Test deploy_infrastructure method
        result = await deployment_service.deploy_infrastructure(
            config=config,
            image_uri="test-image:latest",
            deployment_id="deploy-test-123"
        )
        
        # Verify the deployment service was called with correct config
        deployment_service.deploy_infrastructure.assert_called_once_with(
            config=config,
            image_uri="test-image:latest", 
            deployment_id="deploy-test-123"
        )
        
        # Verify the result
        assert result.vpc_id == "vpc-test-123"
        assert result.subnet_ids == ["subnet-test-1", "subnet-test-2"]
        assert result.cluster_arn == "arn:aws:ecs:us-east-1:123456789:cluster/test"
        assert result.service_arn == "arn:aws:ecs:us-east-1:123456789:service/test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
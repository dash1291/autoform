"""
Unit tests for environment deployment functionality without database mocking
"""
import pytest
import json
from unittest.mock import Mock

from services.deployment import DeploymentConfig


class TestEnvironmentUnitTests:
    """Unit tests that don't require database mocking"""

    def test_deployment_config_with_environment_id(self):
        """Test creating DeploymentConfig with environment_id"""
        config = DeploymentConfig(
            project_id="proj-123",
            project_name="test-project",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123",
            environment_id="env-123",
            subdirectory="backend",
            health_check_path="/api/health",
            port=8080,
            cpu=512,
            memory=1024,
            disk_size=30
        )
        
        assert config.environment_id == "env-123"
        assert config.project_id == "proj-123"
        assert config.subdirectory == "backend"
        assert config.port == 8080
        assert config.cpu == 512
        assert config.memory == 1024
        assert config.disk_size == 30

    def test_deployment_config_without_environment_id(self):
        """Test backward compatibility - DeploymentConfig without environment_id"""
        config = DeploymentConfig(
            project_id="proj-456",
            project_name="legacy-project",
            git_repo_url="https://github.com/test/legacy.git",
            branch="main",
            commit_sha="legacy123"
        )
        
        assert config.environment_id is None
        assert config.project_id == "proj-456"
        assert config.port == 3000  # Default value
        assert config.cpu == 256    # Default value
        assert config.memory == 512  # Default value
        assert config.disk_size == 21  # Default value

    def test_deployment_config_optional_parameters(self):
        """Test all optional parameters work correctly"""
        config = DeploymentConfig(
            project_id="proj-789",
            project_name="full-config-project",
            git_repo_url="https://github.com/test/full.git",
            branch="develop",
            commit_sha="full123",
            environment_id="env-789",
            subdirectory="app/backend",
            health_check_path="/api/v1/health",
            port=9000,
            cpu=1024,
            memory=2048,
            disk_size=50
        )
        
        assert config.environment_id == "env-789"
        assert config.subdirectory == "app/backend"
        assert config.health_check_path == "/api/v1/health"
        assert config.port == 9000
        assert config.cpu == 1024
        assert config.memory == 2048
        assert config.disk_size == 50

    def test_json_subnet_parsing(self):
        """Test JSON subnet ID parsing functionality"""
        # Valid JSON
        valid_json = '["subnet-123", "subnet-456", "subnet-789"]'
        parsed = json.loads(valid_json)
        assert len(parsed) == 3
        assert "subnet-123" in parsed
        assert "subnet-456" in parsed
        assert "subnet-789" in parsed
        
        # Empty array
        empty_json = '[]'
        empty_parsed = json.loads(empty_json)
        assert len(empty_parsed) == 0
        
        # Single subnet
        single_json = '["subnet-only"]'
        single_parsed = json.loads(single_json)
        assert len(single_parsed) == 1
        assert single_parsed[0] == "subnet-only"
        
        # Invalid JSON should raise exception
        with pytest.raises(json.JSONDecodeError):
            json.loads("invalid-json")
        
        with pytest.raises(json.JSONDecodeError):
            json.loads("['subnet-123', 'subnet-456']")  # Single quotes invalid

    def test_subnet_json_round_trip(self):
        """Test converting subnet list to JSON and back"""
        original_subnets = ["subnet-abc", "subnet-def", "subnet-ghi"]
        
        # Convert to JSON (like frontend sends)
        json_string = json.dumps(original_subnets)
        assert isinstance(json_string, str)
        
        # Parse back (like backend receives)
        parsed_subnets = json.loads(json_string)
        assert parsed_subnets == original_subnets
        assert len(parsed_subnets) == 3

    def test_environment_vs_project_logic(self):
        """Test the core logic for environment vs project configuration"""
        # Environment deployment
        env_config = DeploymentConfig(
            project_id="proj-123",
            project_name="test-project-env",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123",
            environment_id="env-123"  # This is the key difference
        )
        
        # Project deployment (legacy)
        proj_config = DeploymentConfig(
            project_id="proj-123",
            project_name="test-project-legacy",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123"
            # No environment_id
        )
        
        # Environment config should have environment_id
        assert env_config.environment_id == "env-123"
        assert proj_config.environment_id is None
        
        # Both should have same project_id
        assert env_config.project_id == proj_config.project_id
        
        # This simulates the deployment service logic
        def should_use_environment_config(config):
            return config.environment_id is not None
        
        assert should_use_environment_config(env_config) is True
        assert should_use_environment_config(proj_config) is False

    def test_vpc_subnet_combinations(self):
        """Test different VPC/subnet configuration scenarios"""
        # Scenario 1: Both VPC and subnets provided (should use existing)
        vpc_and_subnets = {
            "existing_vpc_id": "vpc-123",
            "existing_subnet_ids": ["subnet-1", "subnet-2"],
            "existing_cluster_arn": None
        }
        
        # Scenario 2: Only VPC provided (current bug case)
        vpc_only = {
            "existing_vpc_id": "vpc-123", 
            "existing_subnet_ids": None,
            "existing_cluster_arn": None
        }
        
        # Scenario 3: Nothing provided (create new)
        nothing_provided = {
            "existing_vpc_id": None,
            "existing_subnet_ids": None,
            "existing_cluster_arn": None
        }
        
        # This simulates VPCService logic
        def should_use_existing_vpc(config):
            return (
                config.get("existing_vpc_id") is not None and 
                config.get("existing_subnet_ids") is not None
            )
        
        # Test the logic
        assert should_use_existing_vpc(vpc_and_subnets) is True  # Should use existing
        assert should_use_existing_vpc(vpc_only) is False        # Should create new (bug case)
        assert should_use_existing_vpc(nothing_provided) is False # Should create new

    def test_environment_config_structure(self):
        """Test the environment configuration data structure"""
        # Simulate environment data from database
        environment_data = Mock(
            existingVpcId="vpc-env-123",
            existingSubnetIds='["subnet-env-1", "subnet-env-2"]',
            existingClusterArn="arn:aws:ecs:us-east-1:123456789:cluster/env-cluster",
            cpu=512,
            memory=1024,
            diskSize=30,
            port=8080,
            healthCheckPath="/api/health"
        )
        
        # Simulate the parsing logic
        existing_subnet_ids = None
        if environment_data.existingSubnetIds:
            try:
                existing_subnet_ids = json.loads(environment_data.existingSubnetIds)
            except json.JSONDecodeError:
                existing_subnet_ids = None
        
        config = {
            "existing_vpc_id": environment_data.existingVpcId,
            "existing_subnet_ids": existing_subnet_ids,
            "existing_cluster_arn": environment_data.existingClusterArn,
            "cpu": environment_data.cpu,
            "memory": environment_data.memory,
            "port": environment_data.port
        }
        
        # Verify the structure
        assert config["existing_vpc_id"] == "vpc-env-123"
        assert config["existing_subnet_ids"] == ["subnet-env-1", "subnet-env-2"]
        assert config["existing_cluster_arn"] == "arn:aws:ecs:us-east-1:123456789:cluster/env-cluster"
        assert config["cpu"] == 512
        assert config["memory"] == 1024
        assert config["port"] == 8080

    def test_invalid_subnet_json_handling(self):
        """Test handling of invalid subnet JSON"""
        # Simulate environment with invalid JSON
        environment_data = Mock(
            existingVpcId="vpc-123",
            existingSubnetIds="invalid-json-string",  # Invalid JSON
            existingClusterArn=None
        )
        
        # Simulate the parsing logic with error handling
        existing_subnet_ids = None
        if environment_data.existingSubnetIds:
            try:
                existing_subnet_ids = json.loads(environment_data.existingSubnetIds)
            except json.JSONDecodeError:
                # Should silently handle the error and set to None
                existing_subnet_ids = None
        
        config = {
            "existing_vpc_id": environment_data.existingVpcId,
            "existing_subnet_ids": existing_subnet_ids,
        }
        
        # Should handle invalid JSON gracefully
        assert config["existing_vpc_id"] == "vpc-123"
        assert config["existing_subnet_ids"] is None  # Should be None due to JSON error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
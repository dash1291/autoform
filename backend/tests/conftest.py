"""
Shared pytest fixtures and configuration for integration tests
"""
import os
import pytest
import pytest_asyncio
import boto3
from typing import Dict, Any
import asyncio
from moto import mock_sts, mock_ec2, mock_ecs, mock_iam, mock_elbv2, mock_logs, mock_s3, mock_ecr

# Configure LocalStack endpoints if available, otherwise use moto
LOCALSTACK_ENDPOINT = os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")
USE_LOCALSTACK = os.getenv("USE_LOCALSTACK", "false").lower() == "true"


def get_aws_client(service_name: str, region: str = "us-east-1"):
    """Get AWS client configured for LocalStack or moto"""
    if USE_LOCALSTACK:
        return boto3.client(
            service_name,
            endpoint_url=LOCALSTACK_ENDPOINT,
            region_name=region,
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
    else:
        # For moto, return standard client (moto will mock it)
        return boto3.client(service_name, region_name=region)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def aws_credentials():
    """Test AWS credentials"""
    return {
        "access_key": "test-access-key",
        "secret_key": "test-secret-key"
    }


@pytest.fixture
def test_region():
    """Test AWS region"""
    return "us-east-1"


@pytest.fixture
def mock_aws_services():
    """Mock all AWS services for testing"""
    if not USE_LOCALSTACK:
        # Use moto mocks
        mocks = [
            mock_sts(),
            mock_ec2(),
            mock_ecs(),
            mock_iam(),
            mock_elbv2(),
            mock_logs(),
            mock_s3(),
            mock_ecr()
        ]
        
        for mock in mocks:
            mock.start()
        
        yield
        
        for mock in mocks:
            mock.stop()
    else:
        # LocalStack doesn't need mocking
        yield


@pytest_asyncio.fixture
async def ec2_client(test_region, mock_aws_services):
    """EC2 client for testing"""
    return get_aws_client("ec2", test_region)


@pytest_asyncio.fixture
async def ecs_client(test_region, mock_aws_services):
    """ECS client for testing"""
    return get_aws_client("ecs", test_region)


@pytest_asyncio.fixture
async def iam_client(test_region, mock_aws_services):
    """IAM client for testing"""
    return get_aws_client("iam", test_region)


@pytest_asyncio.fixture
async def elbv2_client(test_region, mock_aws_services):
    """ELBv2 client for testing"""
    return get_aws_client("elbv2", test_region)


@pytest_asyncio.fixture
async def logs_client(test_region, mock_aws_services):
    """CloudWatch Logs client for testing"""
    return get_aws_client("logs", test_region)


@pytest.fixture
def test_project_config():
    """Test project configuration"""
    return {
        "project_name": "test-project",
        "project_id": "test-project-123",
        "port": 3000,
        "cpu": 256,
        "memory": 512,
        "disk_size": 21,
        "health_check_path": "/health",
        "environment_variables": [
            {"key": "NODE_ENV", "value": "production"},
            {"key": "PORT", "value": "3000"}
        ]
    }


@pytest.fixture
def test_deployment_config(test_project_config):
    """Test deployment configuration"""
    from services.deployment import DeploymentConfig
    
    return DeploymentConfig(
        project_id=test_project_config["project_id"],
        project_name=test_project_config["project_name"],
        git_repo_url="https://github.com/test/repo.git",
        branch="main",
        commit_sha="abc123def456",
        health_check_path=test_project_config["health_check_path"],
        port=test_project_config["port"],
        cpu=test_project_config["cpu"],
        memory=test_project_config["memory"],
        disk_size=test_project_config["disk_size"]
    )
"""
Tests for VPC service with environment-specific configurations
"""
import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, MagicMock
import boto3

from infrastructure.services.vpc_service import VPCService
from infrastructure.types import SecurityGroupIds


class TestVPCServiceEnvironmentBehavior:
    """Test VPC service behavior for environment deployments"""

    @pytest.mark.asyncio
    async def test_existing_vpc_and_subnets_no_creation(self, mock_aws_services, ec2_client):
        """Test that when both VPC and subnets are provided, no new resources are created"""
        # Create mock VPC and subnets
        ec2 = ec2_client
        
        # Create a VPC for testing
        vpc_response = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc_response["Vpc"]["VpcId"]
        
        # Create subnets
        subnet1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
        subnet2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")
        subnet_ids = [subnet1["Subnet"]["SubnetId"], subnet2["Subnet"]["SubnetId"]]
        
        # Initialize VPC service with existing resources
        vpc_service = VPCService(
            project_name="test-env-project",
            environment_variables=[],
            region="us-east-1",
            existing_vpc_id=vpc_id,
            existing_subnet_ids=subnet_ids
        )
        
        # Spy on creation methods
        with patch.object(vpc_service, '_create_vpc') as mock_create_vpc, \
             patch.object(vpc_service, '_create_subnets') as mock_create_subnets:
            
            await vpc_service.initialize()
            
            # Verify existing resources were used
            assert vpc_service.vpc_id == vpc_id
            assert vpc_service.subnet_ids == subnet_ids
            
            # Verify no new VPC/subnets were created
            mock_create_vpc.assert_not_called()
            mock_create_subnets.assert_not_called()
            
            # Security groups should still be created
            assert vpc_service.security_group_ids is not None
            assert vpc_service.security_group_ids.alb_security_group_id is not None
            assert vpc_service.security_group_ids.ecs_security_group_id is not None

    @pytest.mark.asyncio
    async def test_only_vpc_provided_creates_new_resources(self, mock_aws_services, ec2_client):
        """Test the bug case: when only VPC is provided (no subnets), it creates new VPC"""
        ec2 = ec2_client
        
        # Create a VPC
        vpc_response = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        existing_vpc_id = vpc_response["Vpc"]["VpcId"]
        
        vpc_service = VPCService(
            project_name="test-bug-case",
            environment_variables=[],
            region="us-east-1",
            existing_vpc_id=existing_vpc_id,
            existing_subnet_ids=None  # This is the bug case!
        )
        
        await vpc_service.initialize()
        
        # Bug behavior: it creates a new VPC instead of using existing
        assert vpc_service.vpc_id != existing_vpc_id
        assert vpc_service.vpc_id != ""
        
        # It also creates new subnets
        assert len(vpc_service.subnet_ids) == 2

    @pytest.mark.asyncio
    async def test_no_existing_resources_creates_all(self, mock_aws_services):
        """Test that when no existing resources are provided, all are created"""
        vpc_service = VPCService(
            project_name="test-new-env",
            environment_variables=[],
            region="us-east-1",
            existing_vpc_id=None,
            existing_subnet_ids=None
        )
        
        await vpc_service.initialize()
        
        # Verify all resources were created
        assert vpc_service.vpc_id is not None
        assert len(vpc_service.subnet_ids) == 2
        assert vpc_service.security_group_ids is not None

    @pytest.mark.asyncio
    async def test_existing_cluster_arn_passthrough(self):
        """Test that existing cluster ARN is properly passed through"""
        # The VPC service doesn't handle clusters, but this tests
        # that the infrastructure args are properly constructed
        from infrastructure.types import ECSInfrastructureArgs
        
        args = ECSInfrastructureArgs(
            project_name="test-project",
            image_uri="test:latest",
            container_port=3000,
            health_check_path="/health",
            region="us-east-1",
            environment_variables=[],
            existing_vpc_id="vpc-123",
            existing_subnet_ids=["subnet-1", "subnet-2"],
            existing_cluster_arn="arn:aws:ecs:us-east-1:123456789:cluster/existing"
        )
        
        assert args.existing_cluster_arn == "arn:aws:ecs:us-east-1:123456789:cluster/existing"

    @pytest.mark.asyncio
    async def test_security_groups_created_for_existing_vpc(self, mock_aws_services, ec2_client):
        """Test that security groups are created even when using existing VPC"""
        ec2 = ec2_client
        
        # Create VPC and subnets
        vpc_response = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc_response["Vpc"]["VpcId"]
        
        subnet1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
        subnet2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24")
        subnet_ids = [subnet1["Subnet"]["SubnetId"], subnet2["Subnet"]["SubnetId"]]
        
        vpc_service = VPCService(
            project_name="test-sg-creation",
            environment_variables=[],
            region="us-east-1",
            existing_vpc_id=vpc_id,
            existing_subnet_ids=subnet_ids
        )
        
        await vpc_service.initialize()
        
        # Verify security groups were created
        alb_sg = ec2.describe_security_groups(
            GroupIds=[vpc_service.security_group_ids.alb_security_group_id]
        )
        assert len(alb_sg["SecurityGroups"]) == 1
        assert alb_sg["SecurityGroups"][0]["VpcId"] == vpc_id
        
        ecs_sg = ec2.describe_security_groups(
            GroupIds=[vpc_service.security_group_ids.ecs_security_group_id]
        )
        assert len(ecs_sg["SecurityGroups"]) == 1
        assert ecs_sg["SecurityGroups"][0]["VpcId"] == vpc_id

    @pytest.mark.asyncio
    async def test_subnet_ids_json_array_handling(self):
        """Test that subnet IDs provided as JSON array are handled correctly"""
        import json
        
        # Simulate environment model with JSON subnet IDs
        subnet_ids_json = json.dumps(["subnet-123", "subnet-456"])
        subnet_ids = json.loads(subnet_ids_json)
        
        vpc_service = VPCService(
            project_name="test-json-subnets",
            environment_variables=[],
            existing_vpc_id="vpc-123",
            existing_subnet_ids=subnet_ids
        )
        
        with patch.object(vpc_service, '_create_security_groups') as mock_create_sgs:
            mock_create_sgs.return_value = SecurityGroupIds(
                alb_security_group_id="sg-alb",
                ecs_security_group_id="sg-ecs"
            )
            
            await vpc_service.initialize()
            
            assert vpc_service.subnet_ids == ["subnet-123", "subnet-456"]


class TestVPCServiceErrorHandling:
    """Test error handling in VPC service"""

    @pytest.mark.asyncio
    async def test_invalid_vpc_id_error(self):
        """Test handling of invalid VPC ID"""
        vpc_service = VPCService(
            project_name="test-invalid",
            environment_variables=[],
            existing_vpc_id="invalid-vpc-id",
            existing_subnet_ids=["subnet-1", "subnet-2"]
        )
        
        # In real implementation, this should validate VPC exists
        # and raise appropriate error
        pass

    @pytest.mark.asyncio
    async def test_subnet_not_in_vpc_error(self):
        """Test handling when subnet doesn't belong to VPC"""
        # In production, should validate subnets belong to VPC
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
import boto3
import base64
import logging
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class EC2CapacityProvider:
    def __init__(
        self,
        project_name: str,
        cluster_name: str,
        vpc_id: str,
        subnet_ids: List[str],
        instance_type: str = "t3a.medium",
        min_size: int = 1,
        max_size: int = 3,
        desired_capacity: int = 1,
        use_spot: bool = True,
        spot_max_price: str = "",
        key_name: str = "",
        target_capacity: int = 80,
        region: str = "us-east-1",
        aws_credentials=None,
    ):
        self.project_name = project_name
        self.cluster_name = cluster_name
        self.vpc_id = vpc_id
        self.subnet_ids = subnet_ids
        self.instance_type = instance_type
        self.min_size = min_size
        self.max_size = max_size
        self.desired_capacity = desired_capacity
        self.use_spot = use_spot
        self.spot_max_price = spot_max_price
        self.key_name = key_name
        self.target_capacity = target_capacity
        self.region = region
        self.aws_credentials = aws_credentials

        # Initialize AWS clients
        from utils.aws_client import create_client
        self.ec2 = create_client("ec2", region, aws_credentials)
        self.autoscaling = create_client("autoscaling", region, aws_credentials)
        self.ecs = create_client("ecs", region, aws_credentials)
        self.iam = create_client("iam", region, aws_credentials)

    def get_latest_ecs_ami(self) -> str:
        """Get the latest ECS-optimized AMI for the region"""
        response = self.ec2.describe_images(
            Owners=["amazon"],
            Filters=[
                {"Name": "name", "Values": ["amzn2-ami-ecs-hvm-*-x86_64-ebs"]},
                {"Name": "state", "Values": ["available"]},
            ],
        )
        
        # Sort by creation date and get the latest
        images = sorted(response["Images"], key=lambda x: x["CreationDate"], reverse=True)
        if not images:
            raise Exception("No ECS-optimized AMI found")
        
        return images[0]["ImageId"]

    def create_ecs_instance_role(self) -> str:
        """Create IAM role for ECS container instances"""
        role_name = f"{self.project_name}-ecs-instance-role"
        
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        
        try:
            # Check if role exists
            self.iam.get_role(RoleName=role_name)
            logger.info(f"IAM role {role_name} already exists")
        except self.iam.exceptions.NoSuchEntityException:
            # Create role
            self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"ECS container instance role for {self.project_name}",
                Tags=[{"Key": "Name", "Value": role_name}],
            )
            
            # Attach policies
            policies = [
                "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role",
                "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            ]
            
            for policy_arn in policies:
                self.iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
            
            logger.info(f"Created IAM role: {role_name}")
        
        # Create instance profile if not exists  
        instance_profile_name = f"{self.project_name}-ecs-profile"
        try:
            profile = self.iam.get_instance_profile(InstanceProfileName=instance_profile_name)
            logger.info(f"Found existing instance profile: {instance_profile_name}")
            
            # Check if role is attached
            if not profile['InstanceProfile']['Roles']:
                logger.info(f"Attaching role {role_name} to instance profile")
                self.iam.add_role_to_instance_profile(
                    InstanceProfileName=instance_profile_name, RoleName=role_name
                )
        except self.iam.exceptions.NoSuchEntityException:
            logger.info(f"Creating new instance profile: {instance_profile_name}")
            self.iam.create_instance_profile(InstanceProfileName=instance_profile_name)
            self.iam.add_role_to_instance_profile(
                InstanceProfileName=instance_profile_name, RoleName=role_name
            )
            logger.info(f"Created instance profile: {instance_profile_name}")
            
            # Wait for instance profile to be available
            time.sleep(5)  # IAM eventual consistency
        
        return instance_profile_name

    def create_security_group(self) -> str:
        """Create security group for ECS container instances"""
        sg_name = f"{self.project_name}-ecs-instance-sg"
        
        try:
            response = self.ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [self.vpc_id]},
                ]
            )
            
            if response["SecurityGroups"]:
                sg_id = response["SecurityGroups"][0]["GroupId"]
                logger.info(f"Using existing security group: {sg_id}")
                return sg_id
        except Exception:
            pass
        
        # Create security group
        response = self.ec2.create_security_group(
            GroupName=sg_name,
            Description=f"Security group for ECS container instances in {self.project_name}",
            VpcId=self.vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": sg_name}],
                }
            ],
        )
        
        sg_id = response["GroupId"]
        
        # Allow all outbound traffic (skip if default rule already exists)
        try:
            self.ec2.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": "-1",
                        "FromPort": -1,
                        "ToPort": -1,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    }
                ],
            )
        except self.ec2.exceptions.ClientError as e:
            if "InvalidPermission.Duplicate" in str(e):
                logger.info("Default egress rule already exists, skipping")
            else:
                raise e
        
        # Configure ingress rules for bridge mode
        self._configure_bridge_mode_ingress_rules(sg_id)
        
        logger.info(f"Created security group: {sg_id}")
        return sg_id
    
    def _configure_bridge_mode_ingress_rules(self, sg_id: str) -> None:
        """Configure security group rules for bridge mode networking"""
        from infrastructure.constants import DEFAULT_DYNAMIC_PORT_RANGE_START, DEFAULT_DYNAMIC_PORT_RANGE_END
        
        # Rules to add for bridge mode
        ingress_rules = [
            {
                "IpProtocol": "tcp",
                "FromPort": DEFAULT_DYNAMIC_PORT_RANGE_START,
                "ToPort": DEFAULT_DYNAMIC_PORT_RANGE_END,
                "IpRanges": [{"CidrIp": "10.0.0.0/8", "Description": "VPC internal traffic for dynamic ports"}],
                "description": "Dynamic port range for ECS bridge mode tasks"
            },
            {
                "IpProtocol": "tcp", 
                "FromPort": 80,
                "ToPort": 80,
                "IpRanges": [{"CidrIp": "10.0.0.0/8", "Description": "VPC internal HTTP traffic"}],
                "description": "HTTP access from load balancer"
            }
        ]
        
        # Add each rule, skip if it already exists
        for rule in ingress_rules:
            try:
                # Create rule dict without the description field (used for logging only)
                rule_description = rule.pop("description", "Unknown rule")
                
                self.ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=[rule]
                )
                logger.info(f"Added ingress rule: {rule_description}")
                
            except self.ec2.exceptions.ClientError as e:
                if "InvalidPermission.Duplicate" in str(e):
                    logger.info(f"Ingress rule already exists: {rule_description}")
                else:
                    logger.warning(f"Could not add ingress rule: {e}")
    
    def add_alb_security_group_rule(self, sg_id: str, alb_sg_id: str) -> None:
        """Add specific rule to allow traffic from ALB security group"""
        from infrastructure.constants import DEFAULT_DYNAMIC_PORT_RANGE_START, DEFAULT_DYNAMIC_PORT_RANGE_END
        
        ingress_rules = [
            {
                "IpProtocol": "tcp",
                "FromPort": DEFAULT_DYNAMIC_PORT_RANGE_START,
                "ToPort": DEFAULT_DYNAMIC_PORT_RANGE_END,
                "UserIdGroupPairs": [{"GroupId": alb_sg_id, "Description": "ALB dynamic port access"}]
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 80,
                "ToPort": 80,
                "UserIdGroupPairs": [{"GroupId": alb_sg_id, "Description": "ALB HTTP access"}]
            }
        ]
        
        for rule in ingress_rules:
            try:
                self.ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=[rule]
                )
                logger.info(f"Added ALB access rule: ports {rule['FromPort']}-{rule['ToPort']}")
            except self.ec2.exceptions.ClientError as e:
                if "InvalidPermission.Duplicate" in str(e):
                    logger.info(f"ALB access rule already exists: ports {rule['FromPort']}-{rule['ToPort']}")
                else:
                    logger.warning(f"Could not add ALB access rule: {e}")

    def get_user_data(self) -> str:
        """Generate user data script for ECS container instances"""
        user_data = f"""#!/bin/bash
echo ECS_CLUSTER={self.cluster_name} >> /etc/ecs/ecs.config
echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config
echo ECS_ENABLE_TASK_IAM_ROLE=true >> /etc/ecs/ecs.config

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Update packages
yum update -y
yum install -y aws-cli

# Enable execute command for debugging
yum install -y https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_64bit/session-manager-plugin.rpm
"""
        return base64.b64encode(user_data.encode()).decode()

    def create_launch_template(self, security_group_id: str, instance_profile_name: str) -> str:
        """Create EC2 launch template for ECS container instances"""
        template_name = f"{self.project_name}-ecs-lt"
        ami_id = self.get_latest_ecs_ami()
        
        launch_template_data = {
            "ImageId": ami_id,
            "InstanceType": self.instance_type,
            "IamInstanceProfile": {"Arn": f"arn:aws:iam::{self.get_account_id()}:instance-profile/{instance_profile_name}"},
            "SecurityGroupIds": [security_group_id],
            "UserData": self.get_user_data(),
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": f"{self.project_name}-ecs-instance"},
                        {"Key": "Cluster", "Value": self.cluster_name},
                    ],
                }
            ],
            "BlockDeviceMappings": [
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {
                        "VolumeSize": 30,
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                    },
                }
            ],
        }
        
        if self.key_name:
            launch_template_data["KeyName"] = self.key_name
        
        if self.use_spot:
            launch_template_data["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                },
            }
            if self.spot_max_price:
                launch_template_data["InstanceMarketOptions"]["SpotOptions"]["MaxPrice"] = self.spot_max_price
        
        try:
            # Check if template exists
            response = self.ec2.describe_launch_templates(
                LaunchTemplateNames=[template_name]
            )
            
            if response["LaunchTemplates"]:
                logger.info(f"Launch template {template_name} already exists, using existing")
                return template_name
        except self.ec2.exceptions.ClientError:
            pass
        
        # Create new template
        response = self.ec2.create_launch_template(
            LaunchTemplateName=template_name,
            LaunchTemplateData=launch_template_data,
        )
        logger.info(f"Created launch template: {template_name}")
        return template_name

    def create_auto_scaling_group(self, launch_template_name: str) -> str:
        """Create Auto Scaling Group for ECS container instances"""
        asg_name = f"{self.project_name}-ecs-asg"
        
        try:
            # Check if ASG exists
            response = self.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            
            if response["AutoScalingGroups"]:
                # Update existing ASG with new launch template
                logger.info(f"Updating ASG {asg_name} to use launch template {launch_template_name}")
                try:
                    self.autoscaling.update_auto_scaling_group(
                        AutoScalingGroupName=asg_name,
                        LaunchTemplate={
                            "LaunchTemplateName": launch_template_name,
                            "Version": "$Latest",
                        },
                        MinSize=self.min_size,
                        MaxSize=self.max_size,
                        DesiredCapacity=self.desired_capacity,
                    )
                    logger.info(f"Updated existing ASG with new launch template: {asg_name}")
                    return asg_name
                except Exception as update_error:
                    logger.error(f"Failed to update ASG: {update_error}")
                    raise update_error
        except self.autoscaling.exceptions.ClientError as e:
            if "does not exist" in str(e):
                logger.info(f"ASG {asg_name} does not exist, will create new one")
            else:
                logger.error(f"Error checking ASG: {e}")
                raise e
        
        # Create new ASG
        self.autoscaling.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchTemplate={
                "LaunchTemplateName": launch_template_name,
                "Version": "$Latest",
            },
            MinSize=self.min_size,
            MaxSize=self.max_size,
            DesiredCapacity=self.desired_capacity,
            VPCZoneIdentifier=",".join(self.subnet_ids),
            HealthCheckType="EC2",
            HealthCheckGracePeriod=300,
            Tags=[
                {
                    "Key": "Name",
                    "Value": f"{self.project_name}-ecs-instance",
                    "PropagateAtLaunch": True,
                },
                {
                    "Key": "Cluster",
                    "Value": self.cluster_name,
                    "PropagateAtLaunch": True,
                },
            ],
            NewInstancesProtectedFromScaleIn=False,
        )
        
        logger.info(f"Created Auto Scaling Group: {asg_name}")
        return asg_name

    def create_capacity_provider(self, asg_name: str) -> str:
        """Create ECS capacity provider"""
        provider_name = f"{self.project_name}-ec2-cp"
        
        try:
            # Check if capacity provider exists
            response = self.ecs.describe_capacity_providers(
                capacityProviders=[provider_name]
            )
            
            if response["capacityProviders"]:
                logger.info(f"Capacity provider {provider_name} already exists")
                return provider_name
        except self.ecs.exceptions.ClientError:
            pass
        
        # Get the actual ASG ARN
        asg_arn = self._get_asg_arn(asg_name)
        
        # Create capacity provider
        self.ecs.create_capacity_provider(
            name=provider_name,
            autoScalingGroupProvider={
                "autoScalingGroupArn": asg_arn,
                "managedScaling": {
                    "status": "ENABLED",
                    "targetCapacity": self.target_capacity,
                    "minimumScalingStepSize": 1,
                    "maximumScalingStepSize": 1,
                },
                "managedTerminationProtection": "DISABLED",
            },
            tags=[{"key": "Name", "value": provider_name}],
        )
        
        logger.info(f"Created capacity provider: {provider_name}")
        return provider_name

    def get_account_id(self) -> str:
        """Get AWS account ID"""
        sts = create_client("sts", self.region, self.aws_credentials)
        return sts.get_caller_identity()["Account"]

    def _get_asg_arn(self, asg_name: str) -> str:
        """Get the actual ARN of an Auto Scaling Group"""
        try:
            response = self.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            
            if response["AutoScalingGroups"]:
                return response["AutoScalingGroups"][0]["AutoScalingGroupARN"]
            else:
                raise Exception(f"Auto Scaling Group {asg_name} not found")
        except Exception as e:
            logger.error(f"Failed to get ASG ARN for {asg_name}: {e}")
            raise e

    def associate_capacity_provider_with_cluster(self, provider_name: str) -> None:
        """Associate capacity provider with ECS cluster"""
        try:
            # Get current cluster settings
            response = self.ecs.describe_clusters(clusters=[self.cluster_name])
            
            if not response["clusters"]:
                logger.error(f"Cluster {self.cluster_name} not found")
                return
            
            cluster = response["clusters"][0]
            current_providers = cluster.get("capacityProviders", [])
            
            if provider_name not in current_providers:
                current_providers.append(provider_name)
                
                # Update cluster with capacity provider
                self.ecs.put_cluster_capacity_providers(
                    cluster=self.cluster_name,
                    capacityProviders=current_providers,
                    defaultCapacityProviderStrategy=[
                        {
                            "capacityProvider": provider_name,
                            "weight": 1,
                            "base": 0,
                        }
                    ],
                )
                
                logger.info(f"Associated capacity provider {provider_name} with cluster")
        except Exception as e:
            logger.error(f"Failed to associate capacity provider: {str(e)}")

    async def setup_ec2_capacity(self) -> Dict[str, Any]:
        """Set up complete EC2 capacity provider infrastructure"""
        logger.info("Setting up EC2 capacity provider infrastructure...")
        
        # Create IAM role and instance profile
        instance_profile_name = self.create_ecs_instance_role()
        
        # Create security group
        security_group_id = self.create_security_group()
        
        # Create launch template
        launch_template_name = self.create_launch_template(security_group_id, instance_profile_name)
        
        # Create Auto Scaling Group
        asg_name = self.create_auto_scaling_group(launch_template_name)
        
        # Create capacity provider
        provider_name = self.create_capacity_provider(asg_name)
        
        # Associate with cluster
        self.associate_capacity_provider_with_cluster(provider_name)
        
        return {
            "capacity_provider_name": provider_name,
            "auto_scaling_group_name": asg_name,
            "launch_template_name": launch_template_name,
            "security_group_id": security_group_id,
            "instance_profile_name": instance_profile_name,
        }


import json
from utils.aws_client import create_client
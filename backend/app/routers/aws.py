from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from core.security import get_current_user
from schemas import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/credentials-check")
async def check_aws_credentials(current_user: User = Depends(get_current_user)):
    """Check AWS credentials and permissions (uses default credentials)"""
    import boto3
    import os
    from botocore.exceptions import ClientError, NoCredentialsError
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        # Test credentials with STS
        sts_client = boto3.client('sts', region_name=region)
        identity = sts_client.get_caller_identity()
        
        # Test CloudWatch logs permissions
        logs_client = boto3.client('logs', region_name=region)
        log_groups = logs_client.describe_log_groups(limit=1)
        
        return {
            "status": "success",
            "account": identity.get('Account'),
            "user_arn": identity.get('Arn'),
            "region": region,
            "cloudwatch_access": True,
            "log_groups_count": len(log_groups.get('logGroups', []))
        }
        
    except NoCredentialsError:
        return {
            "status": "error",
            "message": "No AWS credentials configured",
            "region": region,
            "cloudwatch_access": False
        }
    except ClientError as e:
        return {
            "status": "error",
            "message": f"AWS API error: {e.response['Error']['Message']}",
            "error_code": e.response['Error']['Code'],
            "region": region,
            "cloudwatch_access": False
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "region": region,
            "cloudwatch_access": False
        }


@router.get("/resources")
async def get_aws_resources(current_user: User = Depends(get_current_user)):
    """Get available AWS resources (VPCs, subnets, clusters, etc.) - uses team credentials if available"""
    import boto3
    import os
    from botocore.exceptions import ClientError, NoCredentialsError
    from core.database import prisma
    from services.encryption_service import encryption_service
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        # Try to get team AWS credentials for the user's team
        aws_credentials = None
        logger.info(f"Getting AWS resources for user: {current_user.id}")
        
        # Get user's team if they have one
        user_teams = await prisma.teammember.find_many(
            where={"userId": current_user.id},
            include={"team": True}
        )
        logger.info(f"Found {len(user_teams)} teams for user")
        
        if user_teams:
            # Use the first team's credentials
            team = user_teams[0].team
            logger.info(f"Using team: {team.name} (ID: {team.id})")
            
            team_aws_config = await prisma.teamawsconfig.find_first(
                where={"teamId": team.id, "isActive": True}
            )
            
            if team_aws_config:
                logger.info(f"Found team AWS config for region: {team_aws_config.awsRegion}")
                # Decrypt team credentials
                access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
                secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
                
                if access_key and secret_key:
                    aws_credentials = {
                        "aws_access_key_id": access_key,
                        "aws_secret_access_key": secret_key
                    }
                    region = team_aws_config.awsRegion
                    logger.info(f"Using team credentials for region: {region}")
                else:
                    logger.warning("Failed to decrypt team AWS credentials")
            else:
                logger.info("No active team AWS config found")
        else:
            logger.info("User is not a member of any team")
        
        # Initialize AWS clients with team credentials if available, otherwise use default
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update(aws_credentials)
            logger.info("Using team AWS credentials")
        else:
            logger.info("Using default AWS credentials")
        
        ec2_client = boto3.client('ec2', **client_config)
        ecs_client = boto3.client('ecs', **client_config)
        
        # Get VPCs
        logger.info("Attempting to describe VPCs...")
        vpcs_response = ec2_client.describe_vpcs()
        logger.info(f"Successfully retrieved {len(vpcs_response['Vpcs'])} VPCs")
        vpcs = []
        subnets_by_vpc = {}
        
        for vpc in vpcs_response['Vpcs']:
            vpc_name = vpc.get('VpcId')
            # Try to get name from tags
            for tag in vpc.get('Tags', []):
                if tag['Key'] == 'Name':
                    vpc_name = tag['Value']
                    break
            
            vpc_info = {
                "id": vpc['VpcId'],
                "name": vpc_name,
                "cidrBlock": vpc['CidrBlock'],
                "isDefault": vpc.get('IsDefault', False)
            }
            vpcs.append(vpc_info)
            
            # Get subnets for this VPC
            subnets_response = ec2_client.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc['VpcId']]}]
            )
            
            subnets = []
            for subnet in subnets_response['Subnets']:
                subnet_name = subnet.get('SubnetId')
                # Try to get name from tags
                for tag in subnet.get('Tags', []):
                    if tag['Key'] == 'Name':
                        subnet_name = tag['Value']
                        break
                
                subnet_info = {
                    "id": subnet['SubnetId'],
                    "name": subnet_name,
                    "cidrBlock": subnet['CidrBlock'],
                    "availabilityZone": subnet['AvailabilityZone'],
                    "isPublic": subnet.get('MapPublicIpOnLaunch', False)
                }
                subnets.append(subnet_info)
            
            subnets_by_vpc[vpc['VpcId']] = subnets
        
        # Get ECS clusters
        logger.info("Attempting to list ECS clusters...")
        clusters_response = ecs_client.list_clusters()
        logger.info(f"Successfully retrieved {len(clusters_response['clusterArns'])} cluster ARNs")
        cluster_details = []
        
        if clusters_response['clusterArns']:
            detailed_clusters = ecs_client.describe_clusters(
                clusters=clusters_response['clusterArns']
            )
            
            for cluster in detailed_clusters['clusters']:
                cluster_info = {
                    "arn": cluster['clusterArn'],
                    "name": cluster['clusterName'],
                    "status": cluster['status'],
                    "runningTasksCount": cluster['runningTasksCount'],
                    "activeServicesCount": cluster['activeServicesCount']
                }
                cluster_details.append(cluster_info)
        
        return {
            "vpcs": vpcs,
            "subnetsByVpc": subnets_by_vpc,
            "clusters": cluster_details
        }
        
    except NoCredentialsError:
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": "AWS credentials not configured"
        }
    except ClientError as e:
        logger.error(f"AWS API error: {e.response['Error']['Message']}")
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": f"AWS API error: {e.response['Error']['Message']}"
        }
    except Exception as e:
        logger.error(f"Error fetching AWS resources: {str(e)}")
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": f"Error fetching AWS resources: {str(e)}"
        }
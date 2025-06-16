from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from core.security import get_current_user
from schemas import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/credentials-check")
async def check_aws_credentials(
    credential_type: str = "auto",  # "auto", "personal", "team", "default"
    current_user: User = Depends(get_current_user)
):
    """Check AWS credentials and permissions (type: auto/personal/team/default)"""
    import boto3
    import os
    from botocore.exceptions import ClientError, NoCredentialsError
    from core.database import prisma
    from services.encryption_service import encryption_service
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    aws_credentials = None
    credential_source = "default"
    
    try:
        logger.info(f"Testing {credential_type} AWS credentials for user: {current_user.id}")
        
        if credential_type == "personal":
            # Test only personal credentials
            user_aws_config = await prisma.userawsconfig.find_first(
                where={"userId": current_user.id, "isActive": True}
            )
            
            if not user_aws_config:
                return {
                    "status": "error",
                    "message": "No personal AWS credentials configured",
                    "credentialSource": "personal"
                }
            
            # Decrypt personal credentials
            access_key = encryption_service.decrypt(user_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(user_aws_config.awsSecretAccessKey)
            
            if not access_key or not secret_key:
                return {
                    "status": "error",
                    "message": "Failed to decrypt personal AWS credentials",
                    "credentialSource": "personal"
                }
            
            aws_credentials = {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key
            }
            region = user_aws_config.awsRegion
            credential_source = "personal"
            
        elif credential_type == "team":
            # This should be called with team_id parameter for specific team testing
            # For now, we'll test the first available team
            user_teams = await prisma.teammember.find_many(
                where={"userId": current_user.id},
                include={"team": True}
            )
            
            owned_teams = await prisma.team.find_many(
                where={"ownerId": current_user.id}
            )
            
            if not user_teams and not owned_teams:
                return {
                    "status": "error",
                    "message": "User is not a member of any team",
                    "credentialSource": "team"
                }
            
            team = user_teams[0].team if user_teams else owned_teams[0]
            
            team_aws_config = await prisma.teamawsconfig.find_first(
                where={"teamId": team.id, "isActive": True}
            )
            
            if not team_aws_config:
                return {
                    "status": "error",
                    "message": f"No AWS credentials configured for team {team.name}",
                    "credentialSource": "team"
                }
            
            # Decrypt team credentials
            access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
            
            if not access_key or not secret_key:
                return {
                    "status": "error",
                    "message": "Failed to decrypt team AWS credentials",
                    "credentialSource": "team"
                }
            
            aws_credentials = {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key
            }
            region = team_aws_config.awsRegion
            credential_source = f"team ({team.name})"
            
        elif credential_type == "default":
            # Test default/environment credentials
            aws_credentials = None
            credential_source = "default"
            
        else:  # credential_type == "auto"
            # Auto fallback logic (for backwards compatibility)
            user_teams = await prisma.teammember.find_many(
                where={"userId": current_user.id},
                include={"team": True}
            )
            
            owned_teams = await prisma.team.find_many(
                where={"ownerId": current_user.id}
            )
            
            if user_teams or owned_teams:
                # Use team credentials
                team = user_teams[0].team if user_teams else owned_teams[0]
                
                team_aws_config = await prisma.teamawsconfig.find_first(
                    where={"teamId": team.id, "isActive": True}
                )
                
                if team_aws_config:
                    access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
                    secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
                    
                    if access_key and secret_key:
                        aws_credentials = {
                            "aws_access_key_id": access_key,
                            "aws_secret_access_key": secret_key
                        }
                        region = team_aws_config.awsRegion
                        credential_source = f"team ({team.name})"
            
            # Fallback to personal AWS credentials if no team credentials
            if not aws_credentials:
                user_aws_config = await prisma.userawsconfig.find_first(
                    where={"userId": current_user.id, "isActive": True}
                )
                
                if user_aws_config:
                    access_key = encryption_service.decrypt(user_aws_config.awsAccessKeyId)
                    secret_key = encryption_service.decrypt(user_aws_config.awsSecretAccessKey)
                    
                    if access_key and secret_key:
                        aws_credentials = {
                            "aws_access_key_id": access_key,
                            "aws_secret_access_key": secret_key
                        }
                        region = user_aws_config.awsRegion
                        credential_source = "personal"
        
        # Initialize AWS clients with appropriate credentials
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update(aws_credentials)
        
        # Test credentials with STS
        sts_client = boto3.client('sts', **client_config)
        identity = sts_client.get_caller_identity()
        
        # Test S3 permissions
        s3_client = boto3.client('s3', **client_config)
        try:
            buckets = s3_client.list_buckets()
            bucket_count = len(buckets.get('Buckets', []))
            s3_access = True
        except ClientError:
            bucket_count = 0
            s3_access = False
        
        return {
            "status": "success",
            "accountId": identity.get('Account'),
            "arn": identity.get('Arn'),
            "region": region,
            "credentialSource": credential_source,
            "bucketCount": bucket_count,
            "s3Access": s3_access
        }
        
    except NoCredentialsError:
        return {
            "status": "error",
            "message": "No AWS credentials configured",
            "region": region,
            "credentialSource": credential_source
        }
    except ClientError as e:
        error_message = e.response['Error']['Message']
        
        # Check for permission issues
        if 'AccessDenied' in e.response['Error']['Code'] or 'not authorized' in error_message:
            return {
                "status": "partial",
                "message": f"Credentials valid but lack sufficient permissions: {error_message}",
                "region": region,
                "credentialSource": credential_source,
                "permissionIssue": True
            }
        
        return {
            "status": "error", 
            "message": f"AWS API error: {error_message}",
            "error_code": e.response['Error']['Code'],
            "region": region,
            "credentialSource": credential_source
        }
    except Exception as e:
        logger.error(f"Error testing AWS credentials: {str(e)}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "region": region,
            "credentialSource": credential_source
        }


@router.get("/resources")
async def get_aws_resources(
    credential_type: str = "auto",  # "auto", "personal", "team", "default"  
    team_id: str = None,  # Required when credential_type="team"
    current_user: User = Depends(get_current_user)
):
    """Get available AWS resources (VPCs, subnets, clusters, etc.) using specified credentials"""
    import boto3
    import os
    from botocore.exceptions import ClientError, NoCredentialsError
    from core.database import prisma
    from services.encryption_service import encryption_service
    
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    try:
        aws_credentials = None
        credential_source = "default"
        logger.info(f"Getting AWS resources for user: {current_user.id} with credential_type: {credential_type}")
        
        if credential_type == "personal":
            # Use ONLY personal credentials
            user_aws_config = await prisma.userawsconfig.find_first(
                where={"userId": current_user.id, "isActive": True}
            )
            
            if not user_aws_config:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "No personal AWS credentials configured. Please configure your AWS credentials in Settings."
                }
            
            # Decrypt personal credentials
            access_key = encryption_service.decrypt(user_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(user_aws_config.awsSecretAccessKey)
            
            if not access_key or not secret_key:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "Failed to decrypt personal AWS credentials"
                }
            
            aws_credentials = {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key
            }
            region = user_aws_config.awsRegion
            credential_source = "personal"
            logger.info(f"Using personal AWS credentials for region: {region}")
            
        elif credential_type == "team":
            # Use ONLY team credentials for specified team
            if not team_id:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "team_id parameter is required when credential_type=team"
                }
            
            # Verify user has access to this team
            user_team = await prisma.teammember.find_first(
                where={"userId": current_user.id, "teamId": team_id}
            )
            owned_team = await prisma.team.find_first(
                where={"id": team_id, "ownerId": current_user.id}
            )
            
            if not user_team and not owned_team:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "You don't have access to this team"
                }
            
            team_aws_config = await prisma.teamawsconfig.find_first(
                where={"teamId": team_id, "isActive": True}
            )
            
            if not team_aws_config:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "No AWS credentials configured for this team"
                }
            
            # Decrypt team credentials
            access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
            secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
            
            if not access_key or not secret_key:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "Failed to decrypt team AWS credentials"
                }
            
            aws_credentials = {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key
            }
            region = team_aws_config.awsRegion
            credential_source = f"team"
            logger.info(f"Using team AWS credentials for region: {region}")
            
        elif credential_type == "default":
            # Use default/environment credentials only
            credential_source = "default"
            logger.info("Using default AWS credentials")
            
        else:  # credential_type == "auto"
            # Auto fallback logic (for backwards compatibility)
            # Try personal first, then team, then default
            user_aws_config = await prisma.userawsconfig.find_first(
                where={"userId": current_user.id, "isActive": True}
            )
            
            if user_aws_config:
                # Decrypt personal credentials
                access_key = encryption_service.decrypt(user_aws_config.awsAccessKeyId)
                secret_key = encryption_service.decrypt(user_aws_config.awsSecretAccessKey)
                
                if access_key and secret_key:
                    aws_credentials = {
                        "aws_access_key_id": access_key,
                        "aws_secret_access_key": secret_key
                    }
                    region = user_aws_config.awsRegion
                    credential_source = "personal"
                    logger.info(f"Using personal AWS credentials for region: {region}")
            
            # Fallback to team credentials if no personal credentials
            if not aws_credentials:
                user_teams = await prisma.teammember.find_many(
                    where={"userId": current_user.id},
                    include={"team": True}
                )
                owned_teams = await prisma.team.find_many(
                    where={"ownerId": current_user.id}
                )
                
                if user_teams or owned_teams:
                    team = user_teams[0].team if user_teams else owned_teams[0]
                    
                    team_aws_config = await prisma.teamawsconfig.find_first(
                        where={"teamId": team.id, "isActive": True}
                    )
                    
                    if team_aws_config:
                        access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
                        secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)
                        
                        if access_key and secret_key:
                            aws_credentials = {
                                "aws_access_key_id": access_key,
                                "aws_secret_access_key": secret_key
                            }
                            region = team_aws_config.awsRegion
                            credential_source = f"team ({team.name})"
                            logger.info(f"Using team credentials for region: {region}")
            
            # Final fallback to default credentials
            if not aws_credentials:
                credential_source = "default"
                logger.info("Using default AWS credentials")
        
        # Initialize AWS clients
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update(aws_credentials)
            logger.info(f"Using {credential_source} AWS credentials")
        else:
            logger.info("Using default AWS credentials")
        
        ec2_client = boto3.client('ec2', **client_config)
        ecs_client = boto3.client('ecs', **client_config)
        
        # Get VPCs
        logger.info(f"Attempting to describe VPCs in region: {region}...")
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


@router.get("/user-credentials")
async def get_user_aws_credentials(current_user: User = Depends(get_current_user)):
    """Get user's personal AWS credentials (returns masked version)"""
    from core.database import prisma
    
    user_aws_config = await prisma.userawsconfig.find_first(
        where={"userId": current_user.id, "isActive": True}
    )
    
    if not user_aws_config:
        return {
            "configured": False,
            "region": None
        }
    
    # Return masked credentials for security
    return {
        "configured": True,
        "region": user_aws_config.awsRegion,
        "accessKeyId": f"{'*' * 15}{user_aws_config.awsAccessKeyId[-4:]}" if len(user_aws_config.awsAccessKeyId) > 4 else "****",
        "createdAt": user_aws_config.createdAt,
        "updatedAt": user_aws_config.updatedAt
    }


@router.post("/user-credentials")
async def save_user_aws_credentials(
    credentials: dict,
    current_user: User = Depends(get_current_user)
):
    """Save user's personal AWS credentials"""
    from core.database import prisma
    from services.encryption_service import encryption_service
    
    try:
        access_key = credentials.get("accessKeyId", "").strip()
        secret_key = credentials.get("secretAccessKey", "").strip()
        region = credentials.get("region", "us-east-1").strip()
        
        if not access_key or not secret_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Access Key ID and Secret Access Key are required"
            )
        
        # Encrypt the credentials
        encrypted_access_key = encryption_service.encrypt(access_key)
        encrypted_secret_key = encryption_service.encrypt(secret_key)
        
        # Check if user already has AWS config
        existing_config = await prisma.userawsconfig.find_first(
            where={"userId": current_user.id}
        )
        
        if existing_config:
            # Update existing config
            await prisma.userawsconfig.update(
                where={"id": existing_config.id},
                data={
                    "awsAccessKeyId": encrypted_access_key,
                    "awsSecretAccessKey": encrypted_secret_key,
                    "awsRegion": region,
                    "isActive": True
                }
            )
        else:
            # Create new config
            await prisma.userawsconfig.create(
                data={
                    "userId": current_user.id,
                    "awsAccessKeyId": encrypted_access_key,
                    "awsSecretAccessKey": encrypted_secret_key,
                    "awsRegion": region,
                    "isActive": True
                }
            )
        
        return {"message": "AWS credentials saved successfully"}
        
    except Exception as e:
        logger.error(f"Error saving user AWS credentials: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save AWS credentials: {str(e)}"
        )


@router.delete("/user-credentials")
async def delete_user_aws_credentials(current_user: User = Depends(get_current_user)):
    """Delete user's personal AWS credentials"""
    from core.database import prisma
    
    try:
        # Find and delete the user's AWS config
        existing_config = await prisma.userawsconfig.find_first(
            where={"userId": current_user.id}
        )
        
        if existing_config:
            await prisma.userawsconfig.delete(
                where={"id": existing_config.id}
            )
            return {"message": "AWS credentials deleted successfully"}
        else:
            return {"message": "No AWS credentials found to delete"}
            
    except Exception as e:
        logger.error(f"Error deleting user AWS credentials: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete AWS credentials: {str(e)}"
        )
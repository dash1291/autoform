from fastapi import APIRouter, Depends
import logging
import os
from botocore.exceptions import ClientError, NoCredentialsError

from core.database import get_async_session
from core.security import get_current_user
from sqlmodel import select, and_
from models.team import Team as TeamModel, TeamMember as TeamMemberModel, TeamAwsConfig
from schemas import User
from services.encryption_service import encryption_service
from utils.aws_client import create_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/credentials-check")
async def check_aws_credentials(
    credential_type: str = "auto",  # "auto", "personal", "team", "default"
    current_user: User = Depends(get_current_user),
):
    """Check AWS credentials and permissions (type: auto/personal/team/default)"""
    region = os.getenv("AWS_REGION", "us-east-1")
    aws_credentials = None
    credential_source = "default"

    try:
        logger.info(
            f"Testing {credential_type} AWS credentials for user: {current_user.id}"
        )

        if credential_type == "personal":
            # Personal credentials no longer supported - all projects must use teams
            return {
                "status": "error",
                "message": "Personal AWS credentials are no longer supported. All projects must belong to a team.",
                "credentialSource": "personal",
            }

        elif credential_type == "team":
            # This should be called with team_id parameter for specific team testing
            # For now, we'll test the first available team
            async with get_async_session() as session:
                user_teams_result = await session.execute(
                    select(TeamMemberModel, TeamModel).join(TeamModel).where(TeamMemberModel.user_id == current_user.id)
                )
                user_teams = user_teams_result.all()

                owned_teams_result = await session.execute(
                    select(TeamModel).where(TeamModel.owner_id == current_user.id)
                )
                owned_teams = owned_teams_result.scalars().all()

                if not user_teams and not owned_teams:
                    return {
                        "status": "error",
                        "message": "User is not a member of any team",
                        "credentialSource": "team",
                    }

                team = user_teams[0][1] if user_teams else owned_teams[0]

                team_aws_config_result = await session.execute(
                    select(TeamAwsConfig).where(and_(TeamAwsConfig.team_id == team.id, TeamAwsConfig.is_active == True))
                )
                result = team_aws_config_result.first()
                team_aws_config = result[0] if result else None

                if not team_aws_config:
                    return {
                        "status": "error",
                        "message": f"No AWS credentials configured for team {team.name}",
                        "credentialSource": "team",
                    }

                # Decrypt team credentials
                access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
                secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)

                if not access_key or not secret_key:
                    return {
                        "status": "error",
                        "message": "Failed to decrypt team AWS credentials",
                        "credentialSource": "team",
                    }

                aws_credentials = {
                    "aws_access_key_id": access_key,
                    "aws_secret_access_key": secret_key,
                }
                region = team_aws_config.aws_region
                credential_source = f"team ({team.name})"

        elif credential_type == "default":
            # Test default/environment credentials
            aws_credentials = None
            credential_source = "default"

        else:  # credential_type == "auto"
            # Auto logic - use first available team credentials
            async with get_async_session() as session:
                user_teams_result = await session.execute(
                    select(TeamMemberModel, TeamModel).join(TeamModel).where(TeamMemberModel.user_id == current_user.id)
                )
                user_teams = user_teams_result.all()

                owned_teams_result = await session.execute(
                    select(TeamModel).where(TeamModel.owner_id == current_user.id)
                )
                owned_teams = owned_teams_result.scalars().all()

                if user_teams or owned_teams:
                    # Use team credentials
                    team = user_teams[0][1] if user_teams else owned_teams[0]

                    team_aws_config_result = await session.execute(
                        select(TeamAwsConfig).where(and_(TeamAwsConfig.team_id == team.id, TeamAwsConfig.is_active == True))
                    )
                    result = team_aws_config_result.first()
                    team_aws_config = result[0] if result else None

                    if team_aws_config:
                        access_key = encryption_service.decrypt(
                            team_aws_config.aws_access_key_id
                        )
                        secret_key = encryption_service.decrypt(
                            team_aws_config.aws_secret_access_key
                        )

                        if access_key and secret_key:
                            aws_credentials = {
                                "aws_access_key_id": access_key,
                                "aws_secret_access_key": secret_key,
                            }
                            region = team_aws_config.aws_region
                            credential_source = f"team ({team.name})"

            # No fallback to personal credentials since they don't exist anymore

        # Initialize AWS clients with LocalStack support
        # Convert credentials format for our create_client function
        client_credentials = None
        if aws_credentials:
            client_credentials = {
                "access_key": aws_credentials["aws_access_key_id"],
                "secret_key": aws_credentials["aws_secret_access_key"],
            }

        # Test credentials with STS
        sts_client = create_client("sts", region, client_credentials)
        identity = sts_client.get_caller_identity()

        # Test S3 permissions
        s3_client = create_client("s3", region, client_credentials)
        try:
            buckets = s3_client.list_buckets()
            bucket_count = len(buckets.get("Buckets", []))
            s3_access = True
        except ClientError:
            bucket_count = 0
            s3_access = False

        return {
            "status": "success",
            "accountId": identity.get("Account"),
            "arn": identity.get("Arn"),
            "region": region,
            "credentialSource": credential_source,
            "bucketCount": bucket_count,
            "s3Access": s3_access,
        }

    except NoCredentialsError:
        return {
            "status": "error",
            "message": "No AWS credentials configured",
            "region": region,
            "credentialSource": credential_source,
        }
    except ClientError as e:
        error_message = e.response["Error"]["Message"]

        # Check for permission issues
        if (
            "AccessDenied" in e.response["Error"]["Code"]
            or "not authorized" in error_message
        ):
            return {
                "status": "partial",
                "message": f"Credentials valid but lack sufficient permissions: {error_message}",
                "region": region,
                "credentialSource": credential_source,
                "permissionIssue": True,
            }

        return {
            "status": "error",
            "message": f"AWS API error: {error_message}",
            "error_code": e.response["Error"]["Code"],
            "region": region,
            "credentialSource": credential_source,
        }
    except Exception as e:
        logger.error(f"Error testing AWS credentials: {str(e)}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "region": region,
            "credentialSource": credential_source,
        }


@router.get("/resources")
async def get_aws_resources(
    credential_type: str = "auto",  # "auto", "personal", "team", "default"
    team_id: str = None,  # Required when credential_type="team"
    current_user: User = Depends(get_current_user),
):
    """Get available AWS resources (VPCs, subnets, clusters, etc.) using specified credentials"""
    region = os.getenv("AWS_REGION", "us-east-1")

    try:
        aws_credentials = None
        credential_source = "default"
        logger.info(
            f"Getting AWS resources for user: {current_user.id} with credential_type: {credential_type}"
        )

        if credential_type == "personal":
            # Personal credentials no longer supported
            return {
                "vpcs": [],
                "subnetsByVpc": {},
                "clusters": [],
                "message": "Personal AWS credentials are no longer supported. All projects must belong to a team.",
            }

        elif credential_type == "team":
            # Use ONLY team credentials for specified team
            if not team_id:
                return {
                    "vpcs": [],
                    "subnetsByVpc": {},
                    "clusters": [],
                    "message": "team_id parameter is required when credential_type=team",
                }

            async with get_async_session() as session:
                # Verify user has access to this team
                user_team_result = await session.execute(
                    select(TeamMemberModel).where(and_(TeamMemberModel.user_id == current_user.id, TeamMemberModel.team_id == team_id))
                )
                user_team = user_team_result.scalar_one_or_none()
                
                owned_team_result = await session.execute(
                    select(TeamModel).where(and_(TeamModel.id == team_id, TeamModel.owner_id == current_user.id))
                )
                owned_team = owned_team_result.scalar_one_or_none()

                if not user_team and not owned_team:
                    return {
                        "vpcs": [],
                        "subnetsByVpc": {},
                        "clusters": [],
                        "message": "You don't have access to this team",
                    }

                team_aws_config_result = await session.execute(
                    select(TeamAwsConfig).where(and_(TeamAwsConfig.team_id == team_id, TeamAwsConfig.is_active == True))
                )
                result = team_aws_config_result.first()
                team_aws_config = result[0] if result else None

                if not team_aws_config:
                    return {
                        "vpcs": [],
                        "subnetsByVpc": {},
                        "clusters": [],
                        "message": "No AWS credentials configured for this team",
                    }

                # Decrypt team credentials
                access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
                secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)

                if not access_key or not secret_key:
                    return {
                        "vpcs": [],
                        "subnetsByVpc": {},
                        "clusters": [],
                        "message": "Failed to decrypt team AWS credentials",
                    }

                aws_credentials = {
                    "aws_access_key_id": access_key,
                    "aws_secret_access_key": secret_key,
                }
                region = team_aws_config.aws_region
                credential_source = "team"
                logger.info(f"Using team AWS credentials for region: {region}")

        elif credential_type == "default":
            # Use default/environment credentials only
            credential_source = "default"
            logger.info("Using default AWS credentials")

        else:  # credential_type == "auto"
            # Auto logic - use first available team credentials
            async with get_async_session() as session:
                user_teams_result = await session.execute(
                    select(TeamMemberModel, TeamModel).join(TeamModel).where(TeamMemberModel.user_id == current_user.id)
                )
                user_teams = user_teams_result.all()
                
                owned_teams_result = await session.execute(
                    select(TeamModel).where(TeamModel.owner_id == current_user.id)
                )
                owned_teams = owned_teams_result.scalars().all()

                if user_teams or owned_teams:
                    team = user_teams[0][1] if user_teams else owned_teams[0]

                    team_aws_config_result = await session.execute(
                        select(TeamAwsConfig).where(and_(TeamAwsConfig.team_id == team.id, TeamAwsConfig.is_active == True))
                    )
                    result = team_aws_config_result.first()
                    team_aws_config = result[0] if result else None

                    if team_aws_config:
                        access_key = encryption_service.decrypt(
                            team_aws_config.aws_access_key_id
                        )
                        secret_key = encryption_service.decrypt(
                            team_aws_config.aws_secret_access_key
                        )

                        if access_key and secret_key:
                            aws_credentials = {
                                "aws_access_key_id": access_key,
                                "aws_secret_access_key": secret_key,
                            }
                            region = team_aws_config.aws_region
                            credential_source = f"team ({team.name})"
                            logger.info(f"Using team credentials for region: {region}")

            # Fallback to default credentials if no team credentials
            if not aws_credentials:
                credential_source = "default"
                logger.info("Using default AWS credentials")

        # Initialize AWS clients with LocalStack support
        # Convert credentials format for our create_client function
        client_credentials = None
        if aws_credentials:
            client_credentials = {
                "access_key": aws_credentials["aws_access_key_id"],
                "secret_key": aws_credentials["aws_secret_access_key"],
            }
            logger.info(f"Using {credential_source} AWS credentials")
        else:
            logger.info("Using default AWS credentials")

        ec2_client = create_client("ec2", region, client_credentials)
        ecs_client = create_client("ecs", region, client_credentials)

        # Get VPCs
        logger.info(f"Attempting to describe VPCs in region: {region}...")
        vpcs_response = ec2_client.describe_vpcs()
        
        logger.info(f"Successfully retrieved {len(vpcs_response['Vpcs'])} VPCs")
        vpcs = []
        subnets_by_vpc = {}

        for vpc in vpcs_response["Vpcs"]:
            vpc_name = vpc.get("VpcId")
            # Try to get name from tags
            for tag in vpc.get("Tags", []):
                if tag["Key"] == "Name":
                    vpc_name = tag["Value"]
                    break

            vpc_info = {
                "id": vpc["VpcId"],
                "name": vpc_name,
                "cidrBlock": vpc["CidrBlock"],
                "isDefault": vpc.get("IsDefault", False),
            }
            vpcs.append(vpc_info)

            # Get subnets for this VPC
            subnets_response = ec2_client.describe_subnets(
                Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}]
            )

            subnets = []
            for subnet in subnets_response["Subnets"]:
                subnet_name = subnet.get("SubnetId")
                # Try to get name from tags
                for tag in subnet.get("Tags", []):
                    if tag["Key"] == "Name":
                        subnet_name = tag["Value"]
                        break

                subnet_info = {
                    "id": subnet["SubnetId"],
                    "name": subnet_name,
                    "cidrBlock": subnet["CidrBlock"],
                    "availabilityZone": subnet["AvailabilityZone"],
                    "isPublic": subnet.get("MapPublicIpOnLaunch", False),
                }
                subnets.append(subnet_info)

            subnets_by_vpc[vpc["VpcId"]] = subnets

        # Get ECS clusters
        logger.info("Attempting to list ECS clusters...")
        clusters_response = ecs_client.list_clusters()
        logger.info(
            f"Successfully retrieved {len(clusters_response['clusterArns'])} cluster ARNs"
        )
        cluster_details = []

        if clusters_response["clusterArns"]:
            detailed_clusters = ecs_client.describe_clusters(
                clusters=clusters_response["clusterArns"]
            )

            for cluster in detailed_clusters["clusters"]:
                cluster_info = {
                    "arn": cluster["clusterArn"],
                    "name": cluster["clusterName"],
                    "status": cluster["status"],
                    "runningTasksCount": cluster["runningTasksCount"],
                    "activeServicesCount": cluster["activeServicesCount"],
                }
                cluster_details.append(cluster_info)

        return {
            "vpcs": vpcs,
            "subnetsByVpc": subnets_by_vpc,
            "clusters": cluster_details,
        }

    except NoCredentialsError:
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": "AWS credentials not configured",
        }
    except ClientError as e:
        logger.error(f"AWS API error: {e.response['Error']['Message']}")
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": f"AWS API error: {e.response['Error']['Message']}",
        }
    except Exception as e:
        logger.error(f"Error fetching AWS resources: {str(e)}")
        return {
            "vpcs": [],
            "subnetsByVpc": {},
            "clusters": [],
            "message": f"Error fetching AWS resources: {str(e)}",
        }

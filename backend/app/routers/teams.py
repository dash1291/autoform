from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List, Optional
import secrets
import logging
from datetime import datetime, timedelta

from core.database import prisma
from core.security import get_current_user
from core.config import settings
from schemas import User
from schemas.team import (
    Team,
    TeamCreate,
    TeamUpdate,
    TeamMember,
    TeamMemberRole,
    TeamMemberAdd,
)
from services.github_user_service import github_user_service
from services.encryption_service import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Team])
async def get_user_teams(current_user: User = Depends(get_current_user)):
    """Get all teams that the current user owns or is a member of"""

    # Get teams where user is owner
    owned_teams = await prisma.team.find_many(
        where={"ownerId": current_user.id},
        include={"members": {"include": {"user": True}}},
    )

    # Get teams where user is a member
    member_teams = await prisma.team.find_many(
        where={"members": {"some": {"userId": current_user.id}}},
        include={"members": {"include": {"user": True}}},
    )

    # Combine and deduplicate teams
    all_teams = {}

    for team in owned_teams:
        all_teams[team.id] = {
            **team.__dict__,
            "memberCount": len(team.members),
            "userRole": TeamMemberRole.OWNER,
        }

    for team in member_teams:
        if team.id not in all_teams:
            user_member = next(
                (m for m in team.members if m.userId == current_user.id), None
            )
            all_teams[team.id] = {
                **team.__dict__,
                "memberCount": len(team.members),
                "userRole": user_member.role if user_member else TeamMemberRole.MEMBER,
            }

    return list(all_teams.values())


@router.post("/", response_model=Team, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate, current_user: User = Depends(get_current_user)
):
    """Create a new team"""
    
    logger.info(f"Creating team: {team_data.name} for user {current_user.id}")
    logger.info(f"Team data: {team_data}")

    try:
        # Check if user already has a team with this name
        existing_team = await prisma.team.find_first(
            where={"ownerId": current_user.id, "name": team_data.name}
        )

        if existing_team:
            logger.warning(f"Team with name {team_data.name} already exists for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have a team with this name",
            )

        # Create the team
        team = await prisma.team.create(
            data={
                "name": team_data.name,
                "description": team_data.description,
                "ownerId": current_user.id,
            }
        )

        logger.info(f"User {current_user.id} created team {team.id}: {team.name}")

        return {**team.__dict__, "memberCount": 0, "userRole": TeamMemberRole.OWNER}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team: {str(e)}")
        # For database/Prisma errors, provide more user-friendly messages
        if "UnknownRelationalFieldError" in str(e):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database configuration error. Please contact support."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create team: {str(e)}"
        )


@router.get("/{team_id}", response_model=Team)
async def get_team(team_id: str, current_user: User = Depends(get_current_user)):
    """Get team details"""

    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {"members": {"some": {"userId": current_user.id}}},
            ],
        },
        include={"members": {"include": {"user": True}}},
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )

    # Determine user's role
    user_role = (
        TeamMemberRole.OWNER
        if team.ownerId == current_user.id
        else TeamMemberRole.MEMBER
    )
    if team.ownerId != current_user.id:
        user_member = next(
            (m for m in team.members if m.userId == current_user.id), None
        )
        if user_member:
            user_role = user_member.role

    return {**team.__dict__, "memberCount": len(team.members), "userRole": user_role}


@router.put("/{team_id}", response_model=Team)
async def update_team(
    team_id: str, team_data: TeamUpdate, current_user: User = Depends(get_current_user)
):
    """Update team details (only owner or admin can update)"""

    # Check if user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Prepare update data
    update_data = {}
    if team_data.name is not None:
        update_data["name"] = team_data.name
    if team_data.description is not None:
        update_data["description"] = team_data.description

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    # Update team
    updated_team = await prisma.team.update(where={"id": team_id}, data=update_data)

    # Get member count
    member_count = await prisma.teammember.count(where={"teamId": team_id})

    user_role = (
        TeamMemberRole.OWNER
        if updated_team.ownerId == current_user.id
        else TeamMemberRole.ADMIN
    )

    logger.info(f"Team {team_id} updated by user {current_user.id}")

    return {**updated_team.__dict__, "memberCount": member_count, "userRole": user_role}


@router.delete("/{team_id}")
async def delete_team(team_id: str, current_user: User = Depends(get_current_user)):
    """Delete team (only owner can delete)"""

    # Check if user is the owner of this team
    team = await prisma.team.find_first(
        where={"id": team_id, "ownerId": current_user.id}
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner",
        )

    # Check if team has projects
    project_count = await prisma.project.count(where={"teamId": team_id})

    if project_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete team with {project_count} projects. Move or delete projects first.",
        )

    # Delete team (this will cascade delete members and invitations)
    await prisma.team.delete(where={"id": team_id})

    logger.info(f"Team {team_id} deleted by owner {current_user.id}")

    return {"message": "Team deleted successfully"}


@router.get("/{team_id}/members", response_model=List[TeamMember])
async def get_team_members(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get team members"""

    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {"members": {"some": {"userId": current_user.id}}},
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )

    # Get team members
    members = await prisma.teammember.find_many(
        where={"teamId": team_id}, include={"user": True}
    )

    return members


@router.post("/{team_id}/members")
async def add_team_member(
    team_id: str,
    member_data: TeamMemberAdd,
    current_user: User = Depends(get_current_user),
):
    """Add a user to the team by GitHub username"""

    # Check if user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get the current user's GitHub access token
    access_token = await github_user_service.get_user_github_access_token(
        current_user.id
    )
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub access token not found. Please re-authenticate with GitHub.",
        )

    # Find or create user by GitHub username
    user_id = await github_user_service.find_or_create_user_by_github_username(
        member_data.github_username, access_token
    )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub user '{member_data.github_username}' not found",
        )

    # Check if user is already a member
    existing_member = await prisma.teammember.find_first(
        where={"teamId": team_id, "userId": user_id}
    )

    if existing_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team",
        )

    # Add user to team
    team_member = await prisma.teammember.create(
        data={"teamId": team_id, "userId": user_id, "role": member_data.role},
        include={"user": True},
    )

    logger.info(
        f"User {member_data.github_username} (ID: {user_id}) added to team {team_id} by {current_user.id}"
    )

    return {
        **team_member.__dict__,
        "user": {
            "id": team_member.user.id,
            "name": team_member.user.name,
            "email": team_member.user.email,
            "image": team_member.user.image,
            "githubId": team_member.user.githubId,
        },
    }


@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str, user_id: str, current_user: User = Depends(get_current_user)
):
    """Remove a member from the team"""

    # Check if current user has admin access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Cannot remove the team owner
    if user_id == team.ownerId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the team owner",
        )

    # Find the member to remove
    member = await prisma.teammember.find_first(
        where={"teamId": team_id, "userId": user_id}
    )

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this team",
        )

    # Remove the member
    await prisma.teammember.delete(where={"id": member.id})

    logger.info(f"User {user_id} removed from team {team_id} by {current_user.id}")

    return {"message": "Member removed successfully"}


@router.put("/{team_id}/members/{user_id}/role")
async def update_member_role(
    team_id: str,
    user_id: str,
    role_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update a team member's role"""

    new_role = role_data.get("role")
    if new_role not in [role.value for role in TeamMemberRole]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role"
        )

    # Check if current user is the team owner
    team = await prisma.team.find_first(
        where={"id": team_id, "ownerId": current_user.id}
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner",
        )

    # Cannot change owner role
    if user_id == team.ownerId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the owner's role",
        )

    # Find the member
    member = await prisma.teammember.find_first(
        where={"teamId": team_id, "userId": user_id}
    )

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this team",
        )

    # Update the role
    updated_member = await prisma.teammember.update(
        where={"id": member.id}, data={"role": new_role}
    )

    logger.info(
        f"User {user_id} role updated to {new_role} in team {team_id} by {current_user.id}"
    )

    return {"message": f"Member role updated to {new_role}"}


@router.get("/{team_id}/aws-config")
async def get_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get team AWS configuration (only shows if configured)"""

    # Check if user is team owner or admin
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get AWS config
    aws_config = await prisma.teamawsconfig.find_first(where={"teamId": team_id})

    if not aws_config:
        return {"configured": False, "isActive": False}

    # Decrypt and mask the access key ID for display
    masked_access_key = None
    if aws_config.awsAccessKeyId:
        try:
            decrypted_access_key = encryption_service.decrypt(aws_config.awsAccessKeyId)
            if decrypted_access_key and len(decrypted_access_key) >= 4:
                # Mask the access key ID properly (AKIA... -> AKIA************)
                masked_access_key = (
                    f"{decrypted_access_key[:4]}{'*' * (len(decrypted_access_key) - 4)}"
                )
            else:
                masked_access_key = "****"
        except Exception:
            masked_access_key = "****"

    # Don't expose the actual credentials, just show masked version
    return {
        "configured": True,
        "isActive": aws_config.isActive,
        "awsRegion": aws_config.awsRegion,
        "awsAccessKeyId": masked_access_key,
        "awsSecretAccessKey": "****************************"
        if aws_config.awsSecretAccessKey
        else None,
        "createdAt": aws_config.createdAt,
        "updatedAt": aws_config.updatedAt,
    }


@router.post("/{team_id}/aws-config")
async def create_or_update_team_aws_config(
    team_id: str, config_data: dict, current_user: User = Depends(get_current_user)
):
    """Create or update team AWS configuration"""

    # Check if user is team owner
    team = await prisma.team.find_first(
        where={"id": team_id, "ownerId": current_user.id}
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner",
        )

    # Validate required fields
    aws_access_key_id = config_data.get("awsAccessKeyId")
    aws_secret_access_key = config_data.get("awsSecretAccessKey")
    aws_region = config_data.get("awsRegion", "us-east-1")
    
    # Auto-generate name if not provided
    if "name" in config_data:
        name = config_data["name"]
    else:
        # Check how many configs exist to generate a meaningful name
        existing_configs = await prisma.teamawsconfig.find_many(where={"teamId": team_id})
        if len(existing_configs) == 0:
            name = "Primary"
        else:
            name = f"Config {len(existing_configs) + 1}"

    if not aws_access_key_id or not aws_secret_access_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AWS Access Key ID and Secret Access Key are required",
        )

    # Encrypt credentials
    encrypted_access_key = encryption_service.encrypt(aws_access_key_id)
    encrypted_secret_key = encryption_service.encrypt(aws_secret_access_key)

    # Check if config already exists
    existing_config = await prisma.teamawsconfig.find_first(where={"teamId": team_id})

    if existing_config:
        # Update existing config
        await prisma.teamawsconfig.update(
            where={"id": existing_config.id},
            data={
                "awsAccessKeyId": encrypted_access_key,
                "awsSecretAccessKey": encrypted_secret_key,
                "awsRegion": aws_region,
                "isActive": True,
            },
        )
        logger.info(f"Team {team_id} AWS config updated by {current_user.id}")
        return {"message": "AWS configuration updated successfully"}
    else:
        # Create new config
        await prisma.teamawsconfig.create(
            data={
                "teamId": team_id,
                "name": name,
                "awsAccessKeyId": encrypted_access_key,
                "awsSecretAccessKey": encrypted_secret_key,
                "awsRegion": aws_region,
                "isActive": True,
            }
        )
        logger.info(f"Team {team_id} AWS config created by {current_user.id}")
        return {"message": "AWS configuration created successfully"}


@router.delete("/{team_id}/aws-config")
async def delete_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Delete team AWS configuration"""

    # Check if user is team owner
    team = await prisma.team.find_first(
        where={"id": team_id, "ownerId": current_user.id}
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not the owner",
        )

    # Delete AWS config
    deleted = await prisma.teamawsconfig.delete_many(where={"teamId": team_id})

    if deleted.count > 0:
        logger.info(f"Team {team_id} AWS config deleted by {current_user.id}")
        return {"message": "AWS configuration deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AWS configuration found for this team",
        )


@router.post("/{team_id}/aws-config/test")
async def test_team_aws_config(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Test team AWS configuration by attempting to list S3 buckets"""

    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get AWS config
    aws_config = await prisma.teamawsconfig.find_first(
        where={"teamId": team_id, "isActive": True}
    )

    if not aws_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active AWS configuration found for this team",
        )

    # Decrypt credentials
    access_key = encryption_service.decrypt(aws_config.awsAccessKeyId)
    secret_key = encryption_service.decrypt(aws_config.awsSecretAccessKey)

    if not access_key or not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt AWS credentials",
        )

    # Test AWS credentials
    from utils.aws_client import create_client
    from botocore.exceptions import ClientError

    try:
        # Create credentials dict for AWS client
        aws_credentials = {
            "access_key": access_key,
            "secret_key": secret_key,
        }

        # Create S3 client with team credentials (LocalStack-aware)
        s3_client = create_client("s3", aws_config.awsRegion, aws_credentials)

        # Try to list buckets as a test
        response = s3_client.list_buckets()
        bucket_count = len(response.get("Buckets", []))

        # Also get account info
        sts_client = create_client("sts", aws_config.awsRegion, aws_credentials)

        identity = sts_client.get_caller_identity()

        return {
            "success": True,
            "message": "AWS credentials are valid",
            "accountId": identity.get("Account"),
            "userId": identity.get("UserId"),
            "arn": identity.get("Arn"),
            "bucketCount": bucket_count,
            "region": aws_config.awsRegion,
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        if error_code == "InvalidClientTokenId":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid AWS Access Key ID. Please check your credentials.",
            )
        elif error_code == "SignatureDoesNotMatch":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid AWS Secret Access Key. Please check your credentials.",
            )
        elif error_code in ["UnauthorizedOperation", "AccessDenied", "Forbidden"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="AWS credentials are valid but lack sufficient permissions. Your AWS user needs permissions for S3 and STS services.",
            )
        elif "not authorized to perform" in error_message.lower():
            # Handle specific authorization errors
            if "s3:ListBuckets" in error_message:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="AWS credentials are valid but your user doesn't have permission to list S3 buckets. This is used for testing only - deployments may still work.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="AWS credentials are valid but lack some required permissions. Please ensure your AWS user has appropriate permissions.",
                )
        else:
            # Log the actual AWS error for debugging
            logger.error(
                f"AWS test error for team {team_id}: {error_code} - {error_message}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS credentials test failed: {error_message}",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing AWS credentials: {str(e)}",
        )


# New endpoints for multiple AWS configurations per team


@router.get("/{team_id}/aws-configs")
async def get_team_aws_configs(
    team_id: str, current_user: User = Depends(get_current_user)
):
    """Get all AWS configurations for a team"""

    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN, TeamMemberRole.MEMBER]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get all AWS configs for this team
    aws_configs = await prisma.teamawsconfig.find_many(where={"teamId": team_id})

    configs_response = []
    for config in aws_configs:
        # Decrypt and mask the access key ID for display
        masked_access_key = "****"
        if config.awsAccessKeyId:
            try:
                decrypted_access_key = encryption_service.decrypt(config.awsAccessKeyId)
                if decrypted_access_key and len(decrypted_access_key) >= 4:
                    masked_access_key = f"{decrypted_access_key[:4]}{'*' * (len(decrypted_access_key) - 4)}"
            except Exception:
                pass

        configs_response.append(
            {
                "id": config.id,
                "name": config.name,
                "isActive": config.isActive,
                "awsRegion": config.awsRegion,
                "awsAccessKeyId": masked_access_key,
                "awsSecretAccessKey": "****************************"
                if config.awsSecretAccessKey
                else None,
                "createdAt": config.createdAt,
                "updatedAt": config.updatedAt,
            }
        )

    return configs_response


@router.post("/{team_id}/aws-configs")
async def create_team_aws_config(
    team_id: str, config_data: dict, current_user: User = Depends(get_current_user)
):
    """Create a new AWS configuration for a team"""

    # Check if user is team owner or admin
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Validate required fields
    name = config_data.get("name", "").strip()
    aws_access_key_id = config_data.get("awsAccessKeyId", "").strip()
    aws_secret_access_key = config_data.get("awsSecretAccessKey", "").strip()
    aws_region = config_data.get("awsRegion", "us-east-1").strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configuration name is required",
        )

    if not aws_access_key_id or not aws_secret_access_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AWS Access Key ID and Secret Access Key are required",
        )

    # Check if a config with this name already exists for the team
    existing_config = await prisma.teamawsconfig.find_first(
        where={"teamId": team_id, "name": name}
    )

    if existing_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AWS configuration with name '{name}' already exists for this team",
        )

    # Encrypt credentials
    encrypted_access_key = encryption_service.encrypt(aws_access_key_id)
    encrypted_secret_key = encryption_service.encrypt(aws_secret_access_key)

    # Create new config
    new_config = await prisma.teamawsconfig.create(
        data={
            "teamId": team_id,
            "name": name,
            "awsAccessKeyId": encrypted_access_key,
            "awsSecretAccessKey": encrypted_secret_key,
            "awsRegion": aws_region,
            "isActive": True,
        }
    )

    logger.info(f"Team {team_id} AWS config '{name}' created by {current_user.id}")

    return {
        "message": f"AWS configuration '{name}' created successfully",
        "id": new_config.id,
        "name": new_config.name,
    }


@router.put("/{team_id}/aws-configs/{config_id}")
async def update_team_aws_config(
    team_id: str,
    config_id: str,
    config_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Update an existing AWS configuration for a team"""

    # Check if user is team owner or admin
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get existing config
    existing_config = await prisma.teamawsconfig.find_first(
        where={"id": config_id, "teamId": team_id}
    )

    if not existing_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
        )

    # Validate and prepare update data
    update_data = {}

    if "name" in config_data:
        name = config_data["name"].strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configuration name cannot be empty",
            )

        # Check if another config with this name exists
        if name != existing_config.name:
            name_conflict = await prisma.teamawsconfig.find_first(
                where={"teamId": team_id, "name": name, "id": {"not": config_id}}
            )
            if name_conflict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"AWS configuration with name '{name}' already exists for this team",
                )

        update_data["name"] = name

    if "awsAccessKeyId" in config_data and "awsSecretAccessKey" in config_data:
        aws_access_key_id = config_data["awsAccessKeyId"].strip()
        aws_secret_access_key = config_data["awsSecretAccessKey"].strip()

        if not aws_access_key_id or not aws_secret_access_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="AWS Access Key ID and Secret Access Key are required",
            )

        # Encrypt credentials
        update_data["awsAccessKeyId"] = encryption_service.encrypt(aws_access_key_id)
        update_data["awsSecretAccessKey"] = encryption_service.encrypt(
            aws_secret_access_key
        )

    if "awsRegion" in config_data:
        aws_region = config_data["awsRegion"].strip()
        if aws_region:
            update_data["awsRegion"] = aws_region

    if "isActive" in config_data:
        update_data["isActive"] = bool(config_data["isActive"])

    # Update config
    updated_config = await prisma.teamawsconfig.update(
        where={"id": config_id}, data=update_data
    )

    logger.info(
        f"Team {team_id} AWS config '{updated_config.name}' updated by {current_user.id}"
    )

    return {
        "message": f"AWS configuration '{updated_config.name}' updated successfully",
        "id": updated_config.id,
        "name": updated_config.name,
    }


@router.delete("/{team_id}/aws-configs/{config_id}")
async def delete_team_aws_config(
    team_id: str, config_id: str, current_user: User = Depends(get_current_user)
):
    """Delete an AWS configuration for a team"""

    # Check if user is team owner or admin
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get existing config
    existing_config = await prisma.teamawsconfig.find_first(
        where={"id": config_id, "teamId": team_id}
    )

    if not existing_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
        )

    # Check if this config is being used by any environments
    environments_using_config = await prisma.environment.find_many(
        where={"teamAwsConfigId": config_id}
    )

    if environments_using_config:
        environment_names = [env.name for env in environments_using_config]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete AWS configuration '{existing_config.name}' because it is being used by environments: {', '.join(environment_names)}",
        )

    # Delete config
    await prisma.teamawsconfig.delete(where={"id": config_id})

    logger.info(
        f"Team {team_id} AWS config '{existing_config.name}' deleted by {current_user.id}"
    )

    return {
        "message": f"AWS configuration '{existing_config.name}' deleted successfully"
    }


@router.post("/{team_id}/aws-configs/{config_id}/test")
async def test_specific_team_aws_config(
    team_id: str, config_id: str, current_user: User = Depends(get_current_user)
):
    """Test a specific team AWS configuration"""

    # Check if user has access to this team
    team = await prisma.team.find_first(
        where={
            "id": team_id,
            "OR": [
                {"ownerId": current_user.id},
                {
                    "members": {
                        "some": {
                            "userId": current_user.id,
                            "role": {"in": [TeamMemberRole.ADMIN]},
                        }
                    }
                },
            ],
        }
    )

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or insufficient permissions",
        )

    # Get specific AWS config
    aws_config = await prisma.teamawsconfig.find_first(
        where={"id": config_id, "teamId": team_id}
    )

    if not aws_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AWS configuration not found"
        )

    # Decrypt credentials
    access_key = encryption_service.decrypt(aws_config.awsAccessKeyId)
    secret_key = encryption_service.decrypt(aws_config.awsSecretAccessKey)

    if not access_key or not secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt AWS credentials",
        )

    # Test AWS credentials
    from utils.aws_client import create_client
    from botocore.exceptions import ClientError

    try:
        # Create credentials dict for AWS client
        aws_credentials = {
            "access_key": access_key,
            "secret_key": secret_key,
        }

        # Create S3 client with team credentials (LocalStack-aware)
        s3_client = create_client("s3", aws_config.awsRegion, aws_credentials)

        # Try to list buckets as a test
        response = s3_client.list_buckets()
        bucket_count = len(response.get("Buckets", []))

        # Also get account info
        sts_client = create_client("sts", aws_config.awsRegion, aws_credentials)

        identity = sts_client.get_caller_identity()

        return {
            "success": True,
            "message": f"AWS credentials for '{aws_config.name}' are valid",
            "configName": aws_config.name,
            "accountId": identity.get("Account"),
            "userId": identity.get("UserId"),
            "arn": identity.get("Arn"),
            "bucketCount": bucket_count,
            "region": aws_config.awsRegion,
        }

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        logger.error(
            f"AWS test error for team {team_id} config {config_id}: {error_code} - {error_message}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AWS credentials test failed for '{aws_config.name}': {error_message}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing AWS credentials for '{aws_config.name}': {str(e)}",
        )

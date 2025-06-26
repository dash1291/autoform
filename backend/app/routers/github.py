from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx
import re
import logging

from core.database import prisma
from core.security import get_current_user
from schemas import User

router = APIRouter()
logger = logging.getLogger(__name__)


class ValidateRepoRequest(BaseModel):
    git_repo_url: str = Field(alias="gitRepoUrl")

    class Config:
        populate_by_name = True


class RepositoryInfo(BaseModel):
    name: str
    full_name: str = Field(alias="fullName")
    private: bool
    default_branch: str = Field(alias="defaultBranch")
    description: Optional[str] = None
    branches: List[str]

    class Config:
        populate_by_name = True


class ValidateRepoResponse(BaseModel):
    valid: bool
    repository: Optional[RepositoryInfo] = None
    error: Optional[str] = None
    needs_reauth: bool = Field(False, alias="needsReauth")

    class Config:
        populate_by_name = True


async def get_branch_commit_sha(
    git_repo_url: str, branch: str, current_user: User
) -> str:
    """Get the latest commit SHA for a specific branch"""
    # Parse GitHub URL
    pattern = r"^https://github\.com/([\w.-]+)/([\w.-]+)(?:\.git)?$"
    match = re.match(pattern, git_repo_url)

    if not match:
        raise ValueError("Invalid GitHub repository URL")

    owner, repo = match.groups()

    # Get user's GitHub token
    account = await prisma.account.find_first(
        where={"userId": current_user.id, "provider": "github"}
    )

    if not account or not account.access_token:
        raise ValueError("GitHub account not connected")

    async with httpx.AsyncClient() as client:
        # Get branch information including latest commit
        branch_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}",
            headers={
                "Authorization": f"Bearer {account.access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AutoForm-Backend",
            },
        )

        if branch_response.status_code == 404:
            raise ValueError(f"Branch '{branch}' not found")
        elif branch_response.status_code != 200:
            raise ValueError(
                f"Failed to fetch branch info: {branch_response.status_code}"
            )

        branch_data = branch_response.json()
        return branch_data["commit"]["sha"]


@router.post("/validate-repo", response_model=ValidateRepoResponse)
async def validate_repository(
    request: ValidateRepoRequest, current_user: User = Depends(get_current_user)
):
    """Validate GitHub repository access and fetch branches"""
    logger.info(f"Validating repository: {request.git_repo_url}")

    # Validate GitHub URL format
    pattern = r"^https://github\.com/([\w.-]+)/([\w.-]+)(?:\.git)?$"
    match = re.match(pattern, request.git_repo_url)

    if not match:
        return ValidateRepoResponse(
            valid=False, error="Please provide a valid GitHub repository URL"
        )

    owner, repo = match.groups()

    # Get user's GitHub token
    account = await prisma.account.find_first(
        where={"userId": current_user.id, "provider": "github"}
    )

    if not account or not account.access_token:
        return ValidateRepoResponse(
            valid=False,
            error="GitHub account not connected. Please sign out and sign in again to connect your GitHub account.",
            needs_reauth=True,
        )

    try:
        async with httpx.AsyncClient() as client:
            # Test token validity
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {account.access_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "AutoForm-Backend",
                },
            )

            if user_response.status_code == 401:
                # Token expired
                await prisma.account.update(
                    where={"id": account.id}, data={"access_token": None}
                )

                return ValidateRepoResponse(
                    valid=False,
                    error="Your GitHub session has expired. Please sign out and sign in again to refresh your access.",
                    needs_reauth=True,
                )

            # Get repository info
            repo_response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"Bearer {account.access_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "AutoForm-Backend",
                },
            )

            if repo_response.status_code == 404:
                return ValidateRepoResponse(
                    valid=False,
                    error="Repository not found or you do not have access to this repository",
                )
            elif repo_response.status_code == 403:
                return ValidateRepoResponse(
                    valid=False,
                    error="Access denied. Please ensure you have read access to this repository",
                )
            elif repo_response.status_code != 200:
                return ValidateRepoResponse(
                    valid=False,
                    error=f"Failed to validate repository: {repo_response.status_code}",
                )

            repo_data = repo_response.json()

            # Get branches
            branches = [repo_data["default_branch"]]
            try:
                branches_response = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/branches",
                    headers={
                        "Authorization": f"Bearer {account.access_token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "AutoForm-Backend",
                    },
                    params={"per_page": 100},
                )

                if branches_response.status_code == 200:
                    branches_data = branches_response.json()
                    branches = [branch["name"] for branch in branches_data]
                    logger.info(f"Found {len(branches)} branches")
            except Exception as e:
                logger.warning(f"Failed to fetch branches: {str(e)}")

            return ValidateRepoResponse(
                valid=True,
                repository=RepositoryInfo(
                    name=repo_data["name"],
                    full_name=repo_data["full_name"],
                    private=repo_data["private"],
                    default_branch=repo_data["default_branch"],
                    description=repo_data.get("description"),
                    branches=branches,
                ),
            )

    except Exception as e:
        logger.error(f"GitHub API error: {str(e)}")
        return ValidateRepoResponse(
            valid=False, error="Failed to validate repository access. Please try again."
        )

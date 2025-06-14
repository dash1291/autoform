import httpx
import logging
from typing import Optional, Dict, Any
from core.database import prisma

logger = logging.getLogger(__name__)


class GitHubUserService:
    def __init__(self):
        self.base_url = "https://api.github.com"
    
    async def get_github_user_by_username(self, username: str, access_token: str) -> Optional[Dict[str, Any]]:
        """Get GitHub user information by username using an access token"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/users/{username}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.info(f"GitHub user '{username}' not found")
                    return None
                else:
                    logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching GitHub user '{username}': {str(e)}")
            return None
    
    async def find_or_create_user_by_github_username(self, username: str, access_token: str) -> Optional[str]:
        """
        Find existing user by GitHub username or create a placeholder user.
        Returns user ID if successful, None if GitHub user doesn't exist.
        """
        # First, verify the GitHub user exists
        github_user = await self.get_github_user_by_username(username, access_token)
        if not github_user:
            return None
        
        github_id = str(github_user["id"])
        
        try:
            # Check if user already exists in our database
            existing_user = await prisma.user.find_first(
                where={"githubId": github_id}
            )
            
            if existing_user:
                logger.info(f"Found existing user for GitHub username '{username}': {existing_user.id}")
                return existing_user.id
            
            # Create a new user with GitHub information
            new_user = await prisma.user.create(
                data={
                    "email": github_user.get("email"),  # May be None if private
                    "name": github_user.get("name") or github_user["login"],
                    "githubId": github_id,
                    "image": github_user.get("avatar_url"),
                }
            )
            
            logger.info(f"Created new user for GitHub username '{username}': {new_user.id}")
            return new_user.id
            
        except Exception as e:
            logger.error(f"Error creating user for GitHub username '{username}': {str(e)}")
            return None
    
    async def get_user_github_access_token(self, user_id: str) -> Optional[str]:
        """Get the GitHub access token for a user"""
        try:
            account = await prisma.account.find_first(
                where={
                    "userId": user_id,
                    "provider": "github"
                }
            )
            
            if account and account.access_token:
                return account.access_token
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting GitHub access token for user {user_id}: {str(e)}")
            return None


# Singleton instance
github_user_service = GitHubUserService()
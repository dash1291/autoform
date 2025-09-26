import aiohttp
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class GitHubWebhookService:
    """Service for managing GitHub webhooks automatically"""

    def __init__(self):
        self.github_api_base = "https://api.github.com"

    def _parse_repo_info(self, git_repo_url: str) -> tuple[str, str]:
        """Extract owner and repo name from GitHub URL"""
        # Handle both HTTPS and SSH URLs
        if git_repo_url.startswith("git@github.com:"):
            # SSH format: git@github.com:owner/repo.git
            path = git_repo_url.replace("git@github.com:", "").replace(".git", "")
        else:
            # HTTPS format: https://github.com/owner/repo.git
            parsed = urlparse(git_repo_url)
            path = parsed.path.strip("/").replace(".git", "")

        parts = path.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]

        raise ValueError(f"Invalid GitHub repository URL: {git_repo_url}")

    async def create_webhook(
        self,
        git_repo_url: str,
        webhook_url: str,
        webhook_secret: str,
        access_token: str,
    ) -> Dict[str, Any]:
        """Create a webhook on GitHub repository"""
        try:
            owner, repo = self._parse_repo_info(git_repo_url)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            webhook_data = {
                "name": "web",
                "active": True,
                "events": ["push"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": webhook_secret,
                    "insecure_ssl": "0",
                },
            }

            async with aiohttp.ClientSession() as session:
                # First, check if webhook already exists
                existing_webhook = await self._find_existing_webhook(
                    session, owner, repo, webhook_url, headers
                )

                if existing_webhook:
                    # Update existing webhook
                    webhook_id = existing_webhook["id"]
                    async with session.patch(
                        f"{self.github_api_base}/repos/{owner}/{repo}/hooks/{webhook_id}",
                        json=webhook_data,
                        headers=headers,
                    ) as response:
                        if response.status == 200:
                            webhook = await response.json()
                            logger.info(
                                f"Updated existing webhook {webhook_id} for {owner}/{repo}"
                            )
                            return {
                                "id": webhook["id"],
                                "url": webhook["url"],
                                "test_url": webhook["test_url"],
                                "ping_url": webhook["ping_url"],
                                "updated": True,
                            }
                        else:
                            error_text = await response.text()
                            raise Exception(f"Failed to update webhook: {error_text}")
                else:
                    # Create new webhook
                    async with session.post(
                        f"{self.github_api_base}/repos/{owner}/{repo}/hooks",
                        json=webhook_data,
                        headers=headers,
                    ) as response:
                        if response.status == 201:
                            webhook = await response.json()
                            logger.info(
                                f"Created webhook {webhook['id']} for {owner}/{repo}"
                            )
                            return {
                                "id": webhook["id"],
                                "url": webhook["url"],
                                "test_url": webhook["test_url"],
                                "ping_url": webhook["ping_url"],
                                "created": True,
                            }
                        elif response.status == 422:
                            # Webhook might already exist
                            error_data = await response.json()
                            if "errors" in error_data and any(
                                e.get("message", "").startswith("Hook already exists")
                                for e in error_data["errors"]
                            ):
                                logger.warning(
                                    f"Webhook already exists for {owner}/{repo}"
                                )
                                return {"exists": True}

                        error_text = await response.text()
                        raise Exception(f"Failed to create webhook: {error_text}")

        except Exception as e:
            logger.error(f"Error managing GitHub webhook: {str(e)}")
            raise

    async def _find_existing_webhook(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        webhook_url: str,
        headers: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Find an existing webhook with the same URL"""
        try:
            async with session.get(
                f"{self.github_api_base}/repos/{owner}/{repo}/hooks", headers=headers
            ) as response:
                if response.status == 200:
                    hooks = await response.json()
                    for hook in hooks:
                        if hook.get("config", {}).get("url") == webhook_url:
                            return hook
        except Exception as e:
            logger.error(f"Error checking existing webhooks: {str(e)}")

        return None

    async def delete_webhook(
        self, git_repo_url: str, webhook_url: str, access_token: str
    ) -> bool:
        """Delete a webhook from GitHub repository"""
        try:
            owner, repo = self._parse_repo_info(git_repo_url)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            async with aiohttp.ClientSession() as session:
                # Find the webhook first
                webhook = await self._find_existing_webhook(
                    session, owner, repo, webhook_url, headers
                )

                if not webhook:
                    logger.warning(f"Webhook not found for {owner}/{repo}")
                    return True  # Consider it deleted

                webhook_id = webhook["id"]
                async with session.delete(
                    f"{self.github_api_base}/repos/{owner}/{repo}/hooks/{webhook_id}",
                    headers=headers,
                ) as response:
                    if response.status == 204:
                        logger.info(f"Deleted webhook {webhook_id} from {owner}/{repo}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to delete webhook: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error deleting GitHub webhook: {str(e)}")
            return False

    async def test_webhook(
        self, git_repo_url: str, webhook_url: str, access_token: str
    ) -> bool:
        """Send a test ping to the webhook"""
        try:
            owner, repo = self._parse_repo_info(git_repo_url)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            async with aiohttp.ClientSession() as session:
                # Find the webhook first
                webhook = await self._find_existing_webhook(
                    session, owner, repo, webhook_url, headers
                )

                if not webhook:
                    logger.warning(f"Webhook not found for {owner}/{repo}")
                    return False

                webhook_id = webhook["id"]
                async with session.post(
                    f"{self.github_api_base}/repos/{owner}/{repo}/hooks/{webhook_id}/pings",
                    headers=headers,
                ) as response:
                    if response.status == 204:
                        logger.info(f"Successfully pinged webhook {webhook_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to ping webhook: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error testing GitHub webhook: {str(e)}")
            return False

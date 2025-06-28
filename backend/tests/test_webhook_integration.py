"""
Integration tests for webhook functionality (updated for environment-based architecture)
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
import hmac
import hashlib
import asyncio


class MockWebhook:
    """Mock webhook object"""
    def __init__(self, webhook_id: str, git_repo_url: str, secret: str):
        self.id = webhook_id
        self.gitRepoUrl = git_repo_url
        self.secret = secret
        self.isActive = True
        self.projects = []


class MockProject:
    """Mock project object"""
    def __init__(self, project_id: str, name: str, subdirectory: str = None):
        self.id = project_id
        self.name = name
        self.gitRepoUrl = "https://github.com/test/repo"
        self.branch = "main"
        self.autoDeployEnabled = True
        self.status = "DEPLOYED"
        self.subdirectory = subdirectory
        self.port = 3000
        self.healthCheckPath = "/health"


class MockTeam:
    """Mock team object"""
    def __init__(self, team_id: str, name: str):
        self.id = team_id
        self.name = name


class MockTeamAwsConfig:
    """Mock team AWS config object"""
    def __init__(self, config_id: str, team_id: str):
        self.id = config_id
        self.teamId = team_id
        self.awsRegion = "us-east-1"
        self.awsAccessKeyId = "encrypted-access-key"
        self.awsSecretAccessKey = "encrypted-secret-key"


class MockEnvironment:
    """Mock environment object"""
    def __init__(self, env_id: str, name: str, project: MockProject, branch: str = "main"):
        self.id = env_id
        self.name = name
        self.projectId = project.id
        self.project = project
        self.project.team = MockTeam("team-123", "Test Team")
        self.branch = branch
        self.status = "CREATED"
        self.cpu = 256
        self.memory = 512
        self.diskSize = 21
        self.teamAwsConfig = MockTeamAwsConfig("aws-config-123", "team-123")


@pytest.fixture
def webhook_signature():
    """Generate webhook signature"""
    def _generate_signature(payload_data: dict, secret: str) -> str:
        payload_bytes = json.dumps(payload_data, separators=(",", ":")).encode("utf-8")
        signature = (
            "sha256="
            + hmac.new(
                secret.encode("utf-8"), payload_bytes, hashlib.sha256
            ).hexdigest()
        )
        return signature
    return _generate_signature


class TestWebhookIntegration:
    """Integration tests for webhook functionality"""

    @pytest.mark.asyncio
    async def test_shared_webhook_processes_multiple_projects(self, webhook_signature):
        """Test that a shared webhook can trigger deployments for multiple projects"""
        from app.routers.webhook import github_webhook

        payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/monorepo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Update multiple services",
                    "added": [],
                    "modified": ["frontend/src/app.js", "backend/src/main.py"],
                    "removed": [],
                }
            ],
        }

        # Create webhook shared by multiple projects
        webhook = MockWebhook(
            "shared-webhook-123", "https://github.com/test/monorepo", "shared-secret"
        )

        # Create multiple projects that share this webhook
        frontend_project = MockProject("frontend-123", "frontend-app", "frontend")
        backend_project = MockProject("backend-123", "backend-api", "backend")
        webhook.projects = [frontend_project, backend_project]

        # Create environments for each project
        frontend_env = MockEnvironment("frontend-env-123", "production", frontend_project, "main")
        backend_env = MockEnvironment("backend-env-123", "production", backend_project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        mock_prisma.environment.find_many = AsyncMock(side_effect=[
            [frontend_env],  # First call for frontend project
            [backend_env]    # Second call for backend project
        ])

        deployed_environments = []

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployed_environments.append(environment.id)

        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(payload, "shared-secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_environment_deployment",
            side_effect=mock_trigger_environment_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Both environments should be triggered
            assert "2 environments" in result["message"]
            # Wait for background tasks to complete
            await asyncio.sleep(0.1)
            assert len(deployed_environments) == 2
            assert "frontend-env-123" in deployed_environments
            assert "backend-env-123" in deployed_environments

    @pytest.mark.asyncio
    async def test_webhook_signature_verification_with_shared_secret(self, webhook_signature):
        """Test that webhook signature verification works correctly"""
        from app.routers.webhook import github_webhook

        payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/repo.git"},
            "commits": [{"id": "abc123", "message": "Test commit"}],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "correct-secret"
        )

        project = MockProject("project-123", "test-project")
        webhook.projects = [project]

        # Create environment for project
        env = MockEnvironment("env-123", "production", project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        mock_prisma.environment.find_many = AsyncMock(return_value=[env])

        # Test with correct signature
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        correct_signature = webhook_signature(payload, "correct-secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": correct_signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_environment_deployment"
        ):
            # Should succeed with correct signature
            result = await github_webhook(mock_request, mock_background_tasks)
            assert "1 environment" in result["message"] or "environments" in result

        # Test with incorrect signature
        incorrect_signature = webhook_signature(payload, "wrong-secret")
        mock_request.headers["X-Hub-Signature-256"] = incorrect_signature

        with patch("app.routers.webhook.prisma", mock_prisma):
            # Should fail with incorrect signature
            with pytest.raises(Exception):  # Should raise HTTPException
                await github_webhook(mock_request, mock_background_tasks)

    @pytest.mark.asyncio
    async def test_webhook_filters_projects_by_branch(self, webhook_signature):
        """Test that webhook only triggers deployments for environments matching the branch"""
        from app.routers.webhook import github_webhook

        payload = {
            "ref": "refs/heads/develop",  # Note: develop branch, not main
            "repository": {"clone_url": "https://github.com/test/repo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Feature branch update",
                    "added": [],
                    "modified": ["src/app.js"],
                    "removed": [],
                }
            ],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "secret"
        )

        project = MockProject("project-123", "test-project")
        webhook.projects = [project]

        # Create environments for different branches
        main_env = MockEnvironment("main-env-123", "production", project, "main")
        develop_env = MockEnvironment("develop-env-123", "staging", project, "develop")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        # Mock environment query to return only develop environment (branch filtering)
        mock_prisma.environment.find_many = AsyncMock(return_value=[develop_env])

        deployed_environments = []

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployed_environments.append(environment.id)

        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(payload, "secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_environment_deployment",
            side_effect=mock_trigger_environment_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Wait for background tasks to complete
            await asyncio.sleep(0.1)
            # Only develop environment should be triggered
            assert len(deployed_environments) == 1
            assert "develop-env-123" in deployed_environments
            assert "main-env-123" not in deployed_environments

    @pytest.mark.asyncio
    async def test_webhook_subdirectory_filtering(self, webhook_signature):
        """Test that webhook respects subdirectory filtering for environments"""
        from app.routers.webhook import github_webhook

        # Changes only in frontend directory
        payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/monorepo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Frontend changes only",
                    "added": [],
                    "modified": ["frontend/package.json", "frontend/src/app.js"],
                    "removed": [],
                }
            ],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/monorepo", "secret"
        )

        # Create projects with different subdirectories
        frontend_project = MockProject("frontend-123", "frontend-app", "frontend")
        backend_project = MockProject("backend-123", "backend-api", "backend")
        shared_project = MockProject("shared-123", "shared-lib", None)  # No subdirectory
        webhook.projects = [frontend_project, backend_project, shared_project]

        # Create environments for each project
        frontend_env = MockEnvironment("frontend-env-123", "production", frontend_project, "main")
        backend_env = MockEnvironment("backend-env-123", "production", backend_project, "main")
        shared_env = MockEnvironment("shared-env-123", "production", shared_project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        mock_prisma.environment.find_many = AsyncMock(side_effect=[
            [frontend_env],  # First call for frontend project
            [backend_env],   # Second call for backend project
            [shared_env]     # Third call for shared project
        ])

        deployed_environments = []

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployed_environments.append(environment.id)

        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(payload, "secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_environment_deployment",
            side_effect=mock_trigger_environment_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Wait for background tasks to complete
            await asyncio.sleep(0.1)
            # Frontend and shared environments should be triggered
            # Frontend because changes are in frontend/, shared because it has no subdirectory
            assert len(deployed_environments) == 2
            assert "frontend-env-123" in deployed_environments
            assert "shared-env-123" in deployed_environments
            assert "backend-env-123" not in deployed_environments


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""
Tests for parallel webhook deployments (updated for environment-based architecture)
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
import hmac
import hashlib
import asyncio
import time


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
        self.awsAccessKey = "encrypted-access-key"
        self.awsSecretKey = "encrypted-secret-key"


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
def webhook_payload():
    """Sample GitHub webhook payload"""
    return {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/test/repo.git"},
        "commits": [
            {
                "id": "abc123def456",
                "message": "Update both frontend and backend",
                "added": [],
                "modified": ["frontend/src/app.js", "backend/src/main.py"],
                "removed": [],
            }
        ],
    }


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


class TestParallelWebhookDeployments:
    """Test that webhook deployments run in parallel"""

    @pytest.mark.asyncio
    async def test_multiple_environments_deploy_in_parallel(
        self, webhook_payload, webhook_signature
    ):
        """Test that multiple environments from same webhook deploy concurrently"""
        from app.routers.webhook import github_webhook

        # Create webhook with multiple projects
        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Create projects with different subdirectories that both have changes
        frontend_project = MockProject("frontend-123", "frontend", "frontend")
        backend_project = MockProject("backend-123", "backend", "backend")
        webhook.projects = [frontend_project, backend_project]

        # Create environments for each project
        frontend_env = MockEnvironment("frontend-env-123", "production", frontend_project, "main")
        backend_env = MockEnvironment("backend-env-123", "production", backend_project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        # Mock environment queries to return environments for each project
        mock_prisma.environment.find_many = AsyncMock(side_effect=[
            [frontend_env],  # First call for frontend project
            [backend_env]    # Second call for backend project
        ])

        # Track deployment start times to verify parallel execution
        deployment_times = {}

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployment_times[environment.id] = time.time()
            # Simulate deployment work
            await asyncio.sleep(0.1)
            return f"Deployed {environment.id}"

        # Create request mock
        payload_json = json.dumps(webhook_payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(webhook_payload, "shared-secret")

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

            # Verify both environments were triggered
            assert "2 environments" in result["message"]
            assert len(result.get("environments", [])) == 2

            # Wait a bit for the background tasks to complete
            await asyncio.sleep(0.2)

            # Verify both deployments started (were triggered)
            assert len(deployment_times) == 2
            assert "frontend-env-123" in deployment_times
            assert "backend-env-123" in deployment_times

            # Verify deployments started nearly simultaneously (within 50ms of each other)
            start_times = list(deployment_times.values())
            time_diff = abs(start_times[0] - start_times[1])
            assert (
                time_diff < 0.05
            ), f"Deployments should start in parallel, but had {time_diff}s difference"

    @pytest.mark.asyncio
    async def test_subdirectory_filtering_with_environments(self, webhook_signature):
        """Test that only environments with relevant changes deploy"""
        from app.routers.webhook import github_webhook

        # Payload with changes only in frontend/
        frontend_only_payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/repo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Update frontend only",
                    "added": [],
                    "modified": ["frontend/src/component.js", "frontend/package.json"],
                    "removed": [],
                }
            ],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Create projects with different subdirectories
        frontend_project = MockProject("frontend-123", "frontend", "frontend")
        backend_project = MockProject("backend-123", "backend", "backend")
        docs_project = MockProject("docs-123", "docs", "docs")
        webhook.projects = [frontend_project, backend_project, docs_project]

        # Create environments for each project
        frontend_env = MockEnvironment("frontend-env-123", "production", frontend_project, "main")
        backend_env = MockEnvironment("backend-env-123", "production", backend_project, "main")
        docs_env = MockEnvironment("docs-env-123", "production", docs_project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        # Mock environment queries
        mock_prisma.environment.find_many = AsyncMock(side_effect=[
            [frontend_env],  # First call for frontend project
            [backend_env],   # Second call for backend project  
            [docs_env]       # Third call for docs project
        ])

        deployed_environments = []

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployed_environments.append(environment.id)
            await asyncio.sleep(0.05)  # Simulate work

        payload_json = json.dumps(frontend_only_payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(frontend_only_payload, "shared-secret")

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

            # Wait for background tasks
            await asyncio.sleep(0.1)

            # Only frontend environment should have been deployed due to subdirectory filtering
            assert len(deployed_environments) == 1
            assert "frontend-env-123" in deployed_environments
            assert "backend-env-123" not in deployed_environments
            assert "docs-env-123" not in deployed_environments

    @pytest.mark.asyncio
    async def test_no_environments_matching_branch(self, webhook_payload, webhook_signature):
        """Test webhook when no environments match the branch"""
        from app.routers.webhook import github_webhook

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Create project but no environments for main branch
        project = MockProject("project-123", "myproject")
        webhook.projects = [project]

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        # Mock environment query to return empty list (no environments match branch)
        mock_prisma.environment.find_many = AsyncMock(return_value=[])

        payload_json = json.dumps(webhook_payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(webhook_payload, "shared-secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Should return message about no environments configured
            assert "No environments configured for branch main" in result["message"]

    @pytest.mark.asyncio
    async def test_environments_without_subdirectory_always_deploy(self, webhook_signature):
        """Test that environments without subdirectory deploy on any change"""
        from app.routers.webhook import github_webhook

        # Payload with changes in a specific subdirectory
        specific_payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/repo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Update specific directory",
                    "added": [],
                    "modified": ["some/deep/directory/file.js"],
                    "removed": [],
                }
            ],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Create project without subdirectory (should deploy on any change)
        project = MockProject("project-123", "myproject", None)  # No subdirectory
        webhook.projects = [project]

        # Create environment for project
        env = MockEnvironment("env-123", "production", project, "main")

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        mock_prisma.environment.find_many = AsyncMock(return_value=[env])

        deployed_environments = []

        async def mock_trigger_environment_deployment(environment, payload_data):
            deployed_environments.append(environment.id)

        payload_json = json.dumps(specific_payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(specific_payload, "shared-secret")

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
            # Environment without subdirectory should deploy on any change
            assert len(deployed_environments) == 1
            assert "env-123" in deployed_environments


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
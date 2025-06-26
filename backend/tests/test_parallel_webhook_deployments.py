"""
Tests for parallel webhook deployments
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
    async def test_multiple_projects_deploy_in_parallel(
        self, webhook_payload, webhook_signature
    ):
        """Test that multiple projects from same webhook deploy concurrently"""
        from app.routers.webhook import github_webhook

        # Create webhook with multiple projects
        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Create projects with different subdirectories that both have changes
        frontend_project = MockProject("frontend-123", "frontend", "frontend")
        backend_project = MockProject("backend-123", "backend", "backend")
        webhook.projects = [frontend_project, backend_project]

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)

        # Track deployment start times to verify parallel execution
        deployment_times = {}

        async def mock_trigger_deployment(project_id: str, payload_data):
            deployment_times[project_id] = time.time()
            # Simulate deployment work
            await asyncio.sleep(0.1)
            return f"Deployed {project_id}"

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

        start_time = time.time()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_auto_deployment",
            side_effect=mock_trigger_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Verify both projects were triggered
            assert (
                "2 projects" in result["message"]
                or len(result.get("projects", [])) == 2
            )

            # Wait a bit for the background tasks to complete
            await asyncio.sleep(0.2)

            # Verify both deployments started (were triggered)
            assert len(deployment_times) == 2
            assert "frontend-123" in deployment_times
            assert "backend-123" in deployment_times

            # Verify deployments started nearly simultaneously (within 50ms of each other)
            start_times = list(deployment_times.values())
            time_diff = abs(start_times[0] - start_times[1])
            assert (
                time_diff < 0.05
            ), f"Deployments should start in parallel, but had {time_diff}s difference"

    @pytest.mark.asyncio
    async def test_subdirectory_filtering_with_parallel_deployment(
        self, webhook_signature
    ):
        """Test that only projects with relevant changes deploy, but still in parallel"""
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

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)

        deployed_projects = []

        async def mock_trigger_deployment(project_id: str, payload_data):
            deployed_projects.append(project_id)
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
            "app.routers.webhook.trigger_auto_deployment",
            side_effect=mock_trigger_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Should only trigger frontend project (has changes in frontend/)
            assert "1" in result["message"] or len(result.get("projects", [])) == 1

            # Wait for background task to complete
            await asyncio.sleep(0.1)

            # Verify only frontend project was deployed
            assert len(deployed_projects) == 1
            assert "frontend-123" in deployed_projects

    @pytest.mark.asyncio
    async def test_no_projects_deployed_when_no_changes_match(self, webhook_signature):
        """Test that no deployments are triggered when changes don't match any subdirectories"""
        from app.routers.webhook import github_webhook

        # Payload with changes in a directory that doesn't match any project
        unmatched_payload = {
            "ref": "refs/heads/main",
            "repository": {"clone_url": "https://github.com/test/repo.git"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "Update documentation",
                    "added": [],
                    "modified": ["README.md", "scripts/deploy.sh"],
                    "removed": [],
                }
            ],
        }

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Projects with specific subdirectories
        frontend_project = MockProject("frontend-123", "frontend", "frontend")
        backend_project = MockProject("backend-123", "backend", "backend")
        webhook.projects = [frontend_project, backend_project]

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)

        deployed_projects = []

        async def mock_trigger_deployment(project_id: str, payload_data):
            deployed_projects.append(project_id)

        payload_json = json.dumps(unmatched_payload, separators=(",", ":"))
        payload_bytes = payload_json.encode("utf-8")
        signature = webhook_signature(unmatched_payload, "shared-secret")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "push",
        }
        mock_request.body = AsyncMock(return_value=payload_bytes)
        mock_background_tasks = MagicMock()

        with patch("app.routers.webhook.prisma", mock_prisma), patch(
            "app.routers.webhook.trigger_auto_deployment",
            side_effect=mock_trigger_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Should not trigger any deployments
            assert "No deployments triggered" in result["message"]

            # Verify no deployments were started
            assert len(deployed_projects) == 0

    @pytest.mark.asyncio
    async def test_projects_without_subdirectory_always_deploy(
        self, webhook_payload, webhook_signature
    ):
        """Test that projects without subdirectory always deploy regardless of changed files"""
        from app.routers.webhook import github_webhook

        webhook = MockWebhook(
            "webhook-123", "https://github.com/test/repo", "shared-secret"
        )

        # Mix of projects with and without subdirectories
        monorepo_project = MockProject(
            "monorepo-123", "monorepo", None
        )  # No subdirectory
        frontend_project = MockProject("frontend-123", "frontend", "frontend")
        webhook.projects = [monorepo_project, frontend_project]

        mock_prisma = MagicMock()
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)

        deployed_projects = []

        async def mock_trigger_deployment(project_id: str, payload_data):
            deployed_projects.append(project_id)

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
            "app.routers.webhook.trigger_auto_deployment",
            side_effect=mock_trigger_deployment,
        ):
            result = await github_webhook(mock_request, mock_background_tasks)

            # Should trigger both projects (monorepo always deploys, frontend has changes)
            assert "2" in result["message"] or len(result.get("projects", [])) == 2

            # Wait for background task
            await asyncio.sleep(0.1)

            # Verify both projects were deployed
            assert len(deployed_projects) == 2
            assert "monorepo-123" in deployed_projects
            assert "frontend-123" in deployed_projects


if __name__ == "__main__":
    pytest.main([__file__])

"""
Tests for project webhook configuration endpoints
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException


# Mock classes for testing
class MockUser:
    """Mock user object"""

    def __init__(self, user_id: str = "user-123"):
        self.id = user_id
        self.email = "test@example.com"


class MockProject:
    """Mock project object"""

    def __init__(
        self,
        project_id: str,
        name: str,
        git_repo_url: str,
        webhook_id: str = None,
        team_id: str = None,
        user_id: str = "user-123",
    ):
        self.id = project_id
        self.name = name
        self.gitRepoUrl = git_repo_url
        self.webhookId = webhook_id
        self.teamId = team_id
        self.userId = user_id
        self.branch = "main"
        self.autoDeployEnabled = False
        self.webhookConfigured = False
        self.webhook = None  # Will be set if webhook relationship is loaded


class MockWebhook:
    """Mock webhook object"""

    def __init__(self, webhook_id: str, git_repo_url: str, secret: str):
        self.id = webhook_id
        self.gitRepoUrl = git_repo_url
        self.secret = secret
        self.isActive = True
        self.projects = []


class MockGitHubWebhookService:
    """Mock GitHub webhook service"""

    def __init__(self):
        self.create_webhook = AsyncMock()
        self.delete_webhook = AsyncMock()


@pytest.fixture
def mock_user():
    """Mock user fixture"""
    return MockUser()


@pytest.fixture
def mock_project():
    """Mock project fixture"""
    return MockProject(
        project_id="project-123",
        name="test-project",
        git_repo_url="https://github.com/test/repo",
    )


@pytest.fixture
def mock_project_with_webhook():
    """Mock project with existing webhook"""
    webhook = MockWebhook("webhook-123", "https://github.com/test/repo", "secret-123")
    project = MockProject(
        project_id="project-123",
        name="test-project",
        git_repo_url="https://github.com/test/repo",
        webhook_id="webhook-123",
    )
    project.webhook = webhook
    return project


@pytest.fixture
def mock_webhook():
    """Mock webhook fixture"""
    return MockWebhook("webhook-123", "https://github.com/test/repo", "secret-123")


@pytest.fixture
def mock_prisma():
    """Mock Prisma client"""
    return MagicMock()


@pytest.fixture
def mock_github_webhook_service():
    """Mock GitHub webhook service"""
    return MockGitHubWebhookService()


class TestProjectWebhookConfigure:
    """Test webhook configuration endpoint"""

    @pytest.mark.asyncio
    async def test_configure_webhook_creates_new_webhook(
        self, mock_project, mock_user, mock_prisma, mock_github_webhook_service
    ):
        """Test that configuring webhook creates a new webhook record"""
        from app.routers.projects import configure_webhook

        # Mock project lookup
        mock_prisma.project.find_first = AsyncMock(return_value=mock_project)

        # Mock webhook lookup (not found)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=None)

        # Mock webhook creation
        new_webhook = MockWebhook(
            "new-webhook-123", "https://github.com/test/repo", "new-secret-123"
        )
        mock_prisma.webhook.create = AsyncMock(return_value=new_webhook)

        # Mock project update
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.GitHubWebhookService",
            return_value=mock_github_webhook_service,
        ), patch("app.routers.projects.settings") as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"
            mock_github_webhook_service.create_webhook.return_value = {
                "id": "gh-webhook-123",
                "created": True,
            }

            result = await configure_webhook("project-123", "github-token", mock_user)

            # Verify webhook was created
            mock_prisma.webhook.create.assert_called_once()
            create_args = mock_prisma.webhook.create.call_args[1]["data"]
            assert create_args["gitRepoUrl"] == "https://github.com/test/repo"
            assert "secret" in create_args
            assert create_args["isActive"] is True

            # Verify project was updated with webhook ID
            mock_prisma.project.update.assert_called()

            # Verify GitHub webhook was created
            mock_github_webhook_service.create_webhook.assert_called_once()

            # Verify response
            assert result["webhookUrl"] == "https://api.example.com/api/webhook/github"
            assert result["automatic"] is True
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_configure_webhook_uses_existing_webhook(
        self, mock_project, mock_webhook, mock_user, mock_prisma
    ):
        """Test that configuring webhook uses existing webhook for same repo"""
        from app.routers.projects import configure_webhook

        # Mock project lookup
        mock_prisma.project.find_first = AsyncMock(return_value=mock_project)

        # Mock existing webhook lookup
        mock_prisma.webhook.find_unique = AsyncMock(return_value=mock_webhook)

        # Mock project update
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.settings"
        ) as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result = await configure_webhook("project-123", None, mock_user)

            # Verify webhook was NOT created (existing one used)
            mock_prisma.webhook.create.assert_not_called()

            # Verify project was updated with existing webhook ID
            mock_prisma.project.update.assert_called_once()
            update_args = mock_prisma.project.update.call_args[1]["data"]
            assert update_args["webhookId"] == "webhook-123"

            # Verify response uses existing webhook secret
            assert result["webhookSecret"] == "secret-123"
            assert result["automatic"] is False

    @pytest.mark.asyncio
    async def test_configure_webhook_project_not_found(self, mock_user, mock_prisma):
        """Test webhook configuration when project doesn't exist"""
        from app.routers.projects import configure_webhook

        # Mock project lookup (not found)
        mock_prisma.project.find_first = AsyncMock(return_value=None)

        with patch("app.routers.projects.prisma", mock_prisma):
            with pytest.raises(HTTPException) as exc_info:
                await configure_webhook("nonexistent-project", None, mock_user)

            assert exc_info.value.status_code == 404
            assert "Project not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_configure_webhook_github_api_failure(
        self, mock_project, mock_user, mock_prisma, mock_github_webhook_service
    ):
        """Test webhook configuration when GitHub API fails"""
        from app.routers.projects import configure_webhook

        # Mock project and webhook lookups
        mock_prisma.project.find_first = AsyncMock(return_value=mock_project)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=None)

        new_webhook = MockWebhook(
            "new-webhook-123", "https://github.com/test/repo", "new-secret-123"
        )
        mock_prisma.webhook.create = AsyncMock(return_value=new_webhook)
        mock_prisma.project.update = AsyncMock()

        # Mock GitHub service failure
        mock_github_webhook_service.create_webhook.side_effect = Exception(
            "GitHub API Error"
        )

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.GitHubWebhookService",
            return_value=mock_github_webhook_service,
        ), patch("app.routers.projects.settings") as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result = await configure_webhook("project-123", "github-token", mock_user)

            # Should fall back to manual instructions
            assert result["automatic"] is False
            assert "instructions" in result
            assert result["webhookSecret"] == "new-secret-123"


class TestProjectWebhookDelete:
    """Test webhook deletion endpoint"""

    @pytest.mark.asyncio
    async def test_delete_webhook_removes_project_association(
        self, mock_project_with_webhook, mock_user, mock_prisma
    ):
        """Test that deleting webhook removes project association"""
        from app.routers.projects import delete_webhook_config

        # Mock project lookup with webhook
        mock_prisma.project.find_first = AsyncMock(
            return_value=mock_project_with_webhook
        )

        # Mock no other projects using this webhook
        mock_prisma.project.find_many = AsyncMock(return_value=[])

        # Mock project update and webhook deletion
        mock_prisma.project.update = AsyncMock()
        mock_prisma.webhook.delete = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma):
            result = await delete_webhook_config("project-123", None, mock_user)

            # Verify project was updated to remove webhook association
            mock_prisma.project.update.assert_called_once()
            update_args = mock_prisma.project.update.call_args[1]["data"]
            assert update_args["webhookId"] is None
            assert update_args["autoDeployEnabled"] is False
            # Note: webhookConfigured is now calculated dynamically from webhook relationship

            # Verify webhook was deleted (no other projects using it)
            mock_prisma.webhook.delete.assert_called_once_with(
                where={"id": "webhook-123"}
            )

            assert result["message"] == "Webhook configuration deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_webhook_preserves_shared_webhook(
        self, mock_project_with_webhook, mock_user, mock_prisma
    ):
        """Test that webhook is preserved when other projects share it"""
        from app.routers.projects import delete_webhook_config

        # Mock project lookup with webhook
        mock_prisma.project.find_first = AsyncMock(
            return_value=mock_project_with_webhook
        )

        # Mock other projects using this webhook
        other_project = MockProject(
            "other-project-123",
            "other-project",
            "https://github.com/test/repo",
            "webhook-123",
        )
        mock_prisma.project.find_many = AsyncMock(return_value=[other_project])

        # Mock project update
        mock_prisma.project.update = AsyncMock()
        mock_prisma.webhook.delete = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma):
            result = await delete_webhook_config("project-123", None, mock_user)

            # Verify project was updated
            mock_prisma.project.update.assert_called_once()

            # Verify webhook was NOT deleted (other projects using it)
            mock_prisma.webhook.delete.assert_not_called()

            assert result["message"] == "Webhook configuration deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_webhook_with_github_token(
        self,
        mock_project_with_webhook,
        mock_user,
        mock_prisma,
        mock_github_webhook_service,
    ):
        """Test webhook deletion with GitHub token"""
        from app.routers.projects import delete_webhook_config

        # Mock project lookup
        mock_prisma.project.find_first = AsyncMock(
            return_value=mock_project_with_webhook
        )
        mock_prisma.project.find_many = AsyncMock(return_value=[])
        mock_prisma.project.update = AsyncMock()
        mock_prisma.webhook.delete = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.GitHubWebhookService",
            return_value=mock_github_webhook_service,
        ), patch("app.routers.projects.settings") as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result = await delete_webhook_config(
                "project-123", "github-token", mock_user
            )

            # Verify GitHub webhook deletion was attempted
            mock_github_webhook_service.delete_webhook.assert_called_once_with(
                git_repo_url="https://github.com/test/repo",
                webhook_url="https://api.example.com/api/webhook/github",
                access_token="github-token",
            )

            assert result["message"] == "Webhook configuration deleted successfully"

    @pytest.mark.asyncio
    async def test_delete_webhook_project_not_found(self, mock_user, mock_prisma):
        """Test webhook deletion when project doesn't exist"""
        from app.routers.projects import delete_webhook_config

        # Mock project lookup (not found)
        mock_prisma.project.find_first = AsyncMock(return_value=None)

        with patch("app.routers.projects.prisma", mock_prisma):
            with pytest.raises(HTTPException) as exc_info:
                await delete_webhook_config("nonexistent-project", None, mock_user)

            assert exc_info.value.status_code == 404
            assert "Project not found" in str(exc_info.value.detail)


class TestSharedWebhookScenarios:
    """Test scenarios with shared webhooks"""

    @pytest.mark.asyncio
    async def test_multiple_projects_same_repo_share_webhook(
        self, mock_user, mock_prisma
    ):
        """Test that multiple projects from same repo share webhook"""
        from app.routers.projects import configure_webhook

        # Create two projects with same repo URL
        project1 = MockProject("project-1", "frontend", "https://github.com/test/repo")
        project2 = MockProject("project-2", "backend", "https://github.com/test/repo")

        # Mock existing webhook
        webhook = MockWebhook(
            "shared-webhook", "https://github.com/test/repo", "shared-secret"
        )

        # Test first project configuration
        mock_prisma.project.find_first = AsyncMock(return_value=project1)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=None)
        mock_prisma.webhook.create = AsyncMock(return_value=webhook)
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.settings"
        ) as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result1 = await configure_webhook("project-1", None, mock_user)

            # Verify webhook was created
            assert mock_prisma.webhook.create.called
            assert result1["webhookSecret"] == "shared-secret"

        # Reset mocks for second project
        mock_prisma.reset_mock()

        # Test second project configuration (should use existing webhook)
        mock_prisma.project.find_first = AsyncMock(return_value=project2)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=webhook)
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.settings"
        ) as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result2 = await configure_webhook("project-2", None, mock_user)

            # Verify webhook was NOT created again (reused existing)
            mock_prisma.webhook.create.assert_not_called()
            assert result2["webhookSecret"] == "shared-secret"

    @pytest.mark.asyncio
    async def test_different_repos_get_different_webhooks(self, mock_user, mock_prisma):
        """Test that projects from different repos get different webhooks"""
        from app.routers.projects import configure_webhook

        # Create projects with different repo URLs
        project1 = MockProject("project-1", "frontend", "https://github.com/test/repo1")
        project2 = MockProject("project-2", "backend", "https://github.com/test/repo2")

        webhook1 = MockWebhook("webhook-1", "https://github.com/test/repo1", "secret-1")
        webhook2 = MockWebhook("webhook-2", "https://github.com/test/repo2", "secret-2")

        # Test first project
        mock_prisma.project.find_first = AsyncMock(return_value=project1)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=None)
        mock_prisma.webhook.create = AsyncMock(return_value=webhook1)
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.settings"
        ) as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result1 = await configure_webhook("project-1", None, mock_user)
            assert result1["webhookSecret"] == "secret-1"

        # Reset and test second project
        mock_prisma.reset_mock()
        mock_prisma.project.find_first = AsyncMock(return_value=project2)
        mock_prisma.webhook.find_unique = AsyncMock(return_value=None)
        mock_prisma.webhook.create = AsyncMock(return_value=webhook2)
        mock_prisma.project.update = AsyncMock()

        with patch("app.routers.projects.prisma", mock_prisma), patch(
            "app.routers.projects.settings"
        ) as mock_settings:
            mock_settings.webhook_base_url = "https://api.example.com"

            result2 = await configure_webhook("project-2", None, mock_user)
            assert result2["webhookSecret"] == "secret-2"


if __name__ == "__main__":
    pytest.main([__file__])

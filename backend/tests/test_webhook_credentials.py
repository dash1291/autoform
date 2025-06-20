"""
Integration tests for webhook auto-deployment credential selection
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any

from app.routers.webhook import trigger_auto_deployment


class MockProject:
    """Mock project object"""
    def __init__(self, project_id: str, name: str, team_id: str = None, user_id: str = "user-123"):
        self.id = project_id
        self.name = name
        self.teamId = team_id
        self.userId = user_id
        self.gitRepoUrl = "https://github.com/test/repo.git"
        self.branch = "main"
        self.subdirectory = None
        self.healthCheckPath = "/health"
        self.port = 3000
        self.cpu = 256
        self.memory = 512
        self.diskSize = 21


class MockAwsConfig:
    """Mock AWS configuration object"""
    def __init__(self, access_key: str, secret_key: str, region: str, is_active: bool = True):
        self.awsAccessKeyId = access_key
        self.awsSecretAccessKey = secret_key
        self.awsRegion = region
        self.isActive = is_active


class MockDeployment:
    """Mock deployment object"""
    def __init__(self, deployment_id: str):
        self.id = deployment_id


class MockDeploymentService:
    """Mock deployment service"""
    def __init__(self, region=None, aws_credentials=None):
        self.region = region
        self.aws_credentials = aws_credentials
        self.deploy_project = AsyncMock()


@pytest.fixture
def team_project():
    """Team project fixture"""
    return MockProject(
        project_id="team-project-123",
        name="team-test-project",
        team_id="team-456"
    )


@pytest.fixture
def personal_project():
    """Personal project fixture"""
    return MockProject(
        project_id="personal-project-123",
        name="personal-test-project",
        team_id=None
    )


@pytest.fixture
def team_aws_config():
    """Team AWS configuration fixture"""
    return MockAwsConfig(
        access_key="encrypted-team-access-key",
        secret_key="encrypted-team-secret-key",
        region="us-west-2"
    )


@pytest.fixture
def user_aws_config():
    """User AWS configuration fixture"""
    return MockAwsConfig(
        access_key="encrypted-user-access-key",
        secret_key="encrypted-user-secret-key",
        region="us-east-1"
    )


@pytest.fixture
def webhook_payload():
    """Sample GitHub webhook payload"""
    return {
        "commits": [
            {
                "id": "abc123def456",
                "message": "Fix bug in authentication"
            }
        ]
    }


@pytest.fixture
def mock_encryption_service():
    """Mock encryption service that returns decrypted values"""
    mock_service = MagicMock()
    mock_service.decrypt.side_effect = lambda x: x.replace("encrypted-", "decrypted-")
    return mock_service


@pytest_asyncio.fixture
async def mock_prisma():
    """Mock Prisma client"""
    mock_prisma = MagicMock()
    
    # Mock deployment creation
    async def create_deployment(**kwargs):
        return MockDeployment("deployment-123")
    
    mock_prisma.deployment.create = AsyncMock(side_effect=create_deployment)
    return mock_prisma


class TestWebhookCredentialSelection:
    """Test webhook auto-deployment credential selection"""
    
    @pytest.mark.asyncio
    async def test_team_project_uses_team_credentials(
        self,
        team_project,
        team_aws_config,
        webhook_payload,
        mock_encryption_service,
        mock_prisma
    ):
        """Test that team projects use team AWS credentials"""
        
        # Mock project lookup to return team project
        mock_prisma.project.find_unique = AsyncMock(return_value=team_project)
        
        # Mock team AWS config lookup
        mock_prisma.teamawsconfig.find_first = AsyncMock(return_value=team_aws_config)
        
        # Mock user AWS config lookup (should not be called for team projects)
        mock_prisma.userawsconfig.find_first = AsyncMock(return_value=None)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('services.encryption_service.EncryptionService', return_value=mock_encryption_service):
            
            await trigger_auto_deployment(team_project.id, webhook_payload)
            
            # Verify team credentials were used
            mock_service_class.assert_called_once()
            call_args = mock_service_class.call_args
            assert call_args[1]['region'] == 'us-west-2'
            assert call_args[1]['aws_credentials'] == {
                'access_key': 'decrypted-team-access-key',
                'secret_key': 'decrypted-team-secret-key'
            }
            
            # Verify team AWS config was queried
            mock_prisma.teamawsconfig.find_first.assert_called_once_with(
                where={"teamId": "team-456", "isActive": True}
            )
            
            # Verify user AWS config was NOT queried
            mock_prisma.userawsconfig.find_first.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_personal_project_uses_user_credentials(
        self,
        personal_project,
        user_aws_config,
        webhook_payload,
        mock_encryption_service,
        mock_prisma
    ):
        """Test that personal projects use user AWS credentials"""
        
        # Mock project lookup to return personal project
        mock_prisma.project.find_unique = AsyncMock(return_value=personal_project)
        
        # Mock user AWS config lookup
        mock_prisma.userawsconfig.find_first = AsyncMock(return_value=user_aws_config)
        
        # Mock team AWS config lookup (should not be called for personal projects)
        mock_prisma.teamawsconfig.find_first = AsyncMock(return_value=None)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('services.encryption_service.EncryptionService', return_value=mock_encryption_service):
            
            await trigger_auto_deployment(personal_project.id, webhook_payload)
            
            # Verify user credentials were used
            mock_service_class.assert_called_once()
            call_args = mock_service_class.call_args
            assert call_args[1]['region'] == 'us-east-1'
            assert call_args[1]['aws_credentials'] == {
                'access_key': 'decrypted-user-access-key',
                'secret_key': 'decrypted-user-secret-key'
            }
            
            # Verify user AWS config was queried
            mock_prisma.userawsconfig.find_first.assert_called_once_with(
                where={"userId": "user-123", "isActive": True}
            )
            
            # Verify team AWS config was NOT queried
            mock_prisma.teamawsconfig.find_first.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_team_project_missing_credentials_fails_gracefully(
        self,
        team_project,
        webhook_payload,
        mock_prisma
    ):
        """Test that team projects without credentials fail gracefully"""
        
        # Mock project lookup to return team project
        mock_prisma.project.find_unique = AsyncMock(return_value=team_project)
        
        # Mock missing team AWS config
        mock_prisma.teamawsconfig.find_first = AsyncMock(return_value=None)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('app.routers.webhook.logger') as mock_logger:
            
            await trigger_auto_deployment(team_project.id, webhook_payload)
            
            # Verify deployment service was NOT created
            mock_service_class.assert_not_called()
            
            # Verify error was logged
            mock_logger.error.assert_called_with(
                f"Team project {team_project.id} has no team AWS credentials configured"
            )
    
    @pytest.mark.asyncio
    async def test_personal_project_missing_credentials_fails_gracefully(
        self,
        personal_project,
        webhook_payload,
        mock_prisma
    ):
        """Test that personal projects without credentials fail gracefully"""
        
        # Mock project lookup to return personal project
        mock_prisma.project.find_unique = AsyncMock(return_value=personal_project)
        
        # Mock missing user AWS config
        mock_prisma.userawsconfig.find_first = AsyncMock(return_value=None)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('app.routers.webhook.logger') as mock_logger:
            
            await trigger_auto_deployment(personal_project.id, webhook_payload)
            
            # Verify deployment service was NOT created
            mock_service_class.assert_not_called()
            
            # Verify error was logged
            mock_logger.error.assert_called_with(
                f"Personal project {personal_project.id} has no personal AWS credentials configured"
            )
    
    @pytest.mark.asyncio
    async def test_invalid_credentials_fail_gracefully(
        self,
        team_project,
        webhook_payload,
        mock_prisma
    ):
        """Test that invalid (non-decryptable) credentials fail gracefully"""
        
        # Mock project lookup
        mock_prisma.project.find_unique = AsyncMock(return_value=team_project)
        
        # Mock team AWS config with invalid credentials
        invalid_config = MockAwsConfig("invalid-key", "invalid-secret", "us-west-2")
        mock_prisma.teamawsconfig.find_first = AsyncMock(return_value=invalid_config)
        
        # Mock encryption service that returns None for invalid credentials
        mock_encryption = MagicMock()
        mock_encryption.decrypt.return_value = None
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('services.encryption_service.EncryptionService', return_value=mock_encryption), \
             patch('app.routers.webhook.logger') as mock_logger:
            
            await trigger_auto_deployment(team_project.id, webhook_payload)
            
            # Verify deployment service was NOT created
            mock_service_class.assert_not_called()
            
            # Verify error was logged
            mock_logger.error.assert_called_with(
                f"Team project {team_project.id} has invalid team AWS credentials"
            )
    
    @pytest.mark.asyncio
    async def test_project_not_found_fails_gracefully(
        self,
        webhook_payload,
        mock_prisma
    ):
        """Test that missing projects fail gracefully"""
        
        # Mock project lookup to return None
        mock_prisma.project.find_unique = AsyncMock(return_value=None)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('app.routers.webhook.logger') as mock_logger:
            
            await trigger_auto_deployment("nonexistent-project", webhook_payload)
            
            # Verify deployment service was NOT created
            mock_service_class.assert_not_called()
            
            # Verify error was logged
            mock_logger.error.assert_called_with("Project nonexistent-project not found")
    
    @pytest.mark.asyncio
    async def test_deployment_service_receives_correct_config(
        self,
        team_project,
        team_aws_config,
        webhook_payload,
        mock_encryption_service,
        mock_prisma
    ):
        """Test that DeploymentService receives the correct configuration"""
        
        # Mock project lookup
        mock_prisma.project.find_unique = AsyncMock(return_value=team_project)
        mock_prisma.teamawsconfig.find_first = AsyncMock(return_value=team_aws_config)
        
        with patch('app.routers.webhook.prisma', mock_prisma), \
             patch('app.routers.webhook.DeploymentService') as mock_service_class, \
             patch('services.encryption_service.EncryptionService', return_value=mock_encryption_service):
            
            await trigger_auto_deployment(team_project.id, webhook_payload)
            
            # Verify deployment service was created with correct parameters
            mock_service_class.assert_called_once_with(
                region='us-west-2',
                aws_credentials={
                    'access_key': 'decrypted-team-access-key',
                    'secret_key': 'decrypted-team-secret-key'
                }
            )
            
            # Verify deploy_project was called
            service_instance = mock_service_class.return_value
            service_instance.deploy_project.assert_called_once()
            
            # Check the deployment config passed to deploy_project
            call_args = service_instance.deploy_project.call_args[1]
            config = call_args['config']
            assert config.project_id == team_project.id
            assert config.project_name == team_project.name
            assert config.git_repo_url == team_project.gitRepoUrl
            assert config.branch == team_project.branch
            assert config.commit_sha == "abc123def456"


if __name__ == "__main__":
    pytest.main([__file__])
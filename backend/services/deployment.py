import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from utils.aws_client import create_client

from infrastructure.types import (
    ECSInfrastructureArgs,
    ECSInfrastructureOutput,
    EnvironmentVariable,
)
from infrastructure import ECSInfrastructure
from core.database import get_async_session
from sqlmodel import select, Session
from models.deployment import Deployment, DeploymentStatus
from models.project import Project
from models.environment import Environment, EnvironmentVariable as EnvVarModel
from models.user import Account
from models.team import Team, TeamMember
from services.encryption_service import encryption_service
from services.deployment_manager import deployment_manager
from services.buildpack_service import BuildpackService

logger = logging.getLogger(__name__)


class DeploymentConfig:
    def __init__(
        self,
        project_id: str,
        project_name: str,
        git_repo_url: str,
        branch: str,
        commit_sha: str,
        environment_id: Optional[str] = None,
        subdirectory: Optional[str] = None,
        health_check_path: str = "/",
        port: int = 3000,
        cpu: int = 256,
        memory: int = 512,
        disk_size: int = 21,
        desired_instance_count: int = 1,
        aws_region: Optional[str] = None,
        aws_credentials: Optional[dict] = None,
    ):
        self.project_id = project_id
        self.project_name = project_name
        self.git_repo_url = git_repo_url
        self.branch = branch
        self.commit_sha = commit_sha
        self.environment_id = environment_id
        self.subdirectory = subdirectory
        self.health_check_path = health_check_path
        self.port = port
        self.cpu = cpu
        self.memory = memory
        self.disk_size = disk_size
        self.desired_instance_count = desired_instance_count
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self.aws_credentials = aws_credentials
    
    def dict(self):
        """Convert to dictionary for serialization"""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "git_repo_url": self.git_repo_url,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "environment_id": self.environment_id,
            "subdirectory": self.subdirectory,
            "health_check_path": self.health_check_path,
            "port": self.port,
            "cpu": self.cpu,
            "memory": self.memory,
            "disk_size": self.disk_size,
            "desired_instance_count": self.desired_instance_count,
            "aws_region": self.aws_region,
            "aws_credentials": self.aws_credentials,
        }


class DeploymentService:
    def __init__(self, region: str = None, aws_credentials: Optional[dict] = None):
        if region is None:
            region = os.getenv("AWS_REGION", "us-east-1")
        self.region = region
        self.deployment_logs: Dict[str, List[str]] = {}
        self.aws_credentials = aws_credentials

        # Initialize AWS clients with custom credentials if provided
        self.sts = create_client("sts", region, aws_credentials)
        self.ecr = create_client("ecr", region, aws_credentials)
        self.s3 = create_client("s3", region, aws_credentials)
        self.codebuild = create_client("codebuild", region, aws_credentials)
        self.cloudwatch_logs = create_client("logs", region, aws_credentials)
        self.secretsmanager = create_client("secretsmanager", region, aws_credentials)
        
    async def _get_codebuild_env_vars(self):
        """Get environment variables for CodeBuild, including Autoform's Docker Hub credentials"""
        env_vars = []
        
        try:
            # Read Autoform's Docker Hub credentials using default/autoform credentials
            from utils.aws_client import create_client
            autoform_secrets_client = create_client("secretsmanager", self.region, None)  # Autoform's credentials
            
            # Get Docker Hub credentials from Autoform's Secrets Manager
            response = autoform_secrets_client.get_secret_value(SecretId="dockerhub-credentials")
            import json
            docker_creds = json.loads(response["SecretString"])
            
            env_vars.extend([
                {
                    "name": "DOCKERHUB_USERNAME",
                    "value": docker_creds.get("username", ""),
                    "type": "PLAINTEXT"
                },
                {
                    "name": "DOCKERHUB_PASSWORD", 
                    "value": docker_creds.get("password", ""),
                    "type": "PLAINTEXT"
                }
            ])
            
        except Exception as e:
            # If can't get Docker Hub credentials, just log and continue without them
            logger.warning(f"Could not retrieve Autoform Docker Hub credentials: {e}")
        
        return env_vars
        

    async def log_to_database(self, deployment_id: str, message: str):
        """Log message to database and local storage"""
        try:
            timestamp = datetime.now().isoformat()
            log_message = f"[{timestamp}] {message}"

            # Store in local logs
            if deployment_id not in self.deployment_logs:
                self.deployment_logs[deployment_id] = []
            self.deployment_logs[deployment_id].append(log_message)

            # Update database with current logs
            try:
                async with get_async_session() as session:
                    result = await session.execute(
                        select(Deployment).where(Deployment.id == deployment_id)
                    )
                    deployment = result.scalar_one_or_none()
                    
                    if deployment:
                        logs_text = "\n".join(self.deployment_logs[deployment_id])
                        deployment.logs = logs_text
                        deployment.updated_at = datetime.now()
                        session.add(deployment)
                        await session.commit()
            except Exception as db_error:
                logger.error(f"Failed to update deployment logs in database: {db_error}")

            logger.info(f"[{deployment_id}] {message}")
        except Exception as error:
            logger.error(f"Failed to log to database: {error}")

    async def check_if_aborted(self, deployment_id: Optional[str], update_db: bool = True) -> bool:
        """Check if deployment has been aborted"""
        if deployment_id and deployment_manager.is_deployment_aborted(deployment_id):
            if update_db:
                await self.log_to_database(deployment_id, "❌ Deployment aborted by user")
                # Update deployment status to failed (only do this once)
                try:
                    async with get_async_session() as session:
                        result = await session.execute(
                            select(Deployment).where(Deployment.id == deployment_id)
                        )
                        deployment = result.scalar_one_or_none()
                        if deployment:
                            deployment.status = DeploymentStatus.FAILED
                            deployment.updated_at = datetime.now()
                            session.add(deployment)
                            await session.commit()
                except Exception:
                    # Status may have already been updated, ignore this error
                    pass
            return True
        return False

    def mask_sensitive_command(self, command: str) -> str:
        """Mask sensitive information in commands before logging"""
        # Mask GitHub tokens in URLs (both gho_ and ghp_ patterns)
        masked = re.sub(
            r'https://([^@]+)@github\.com',
            r'https://***@github.com',
            command
        )
        
        # Mask AWS credentials
        masked = re.sub(
            r'(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN)=\S+',
            r'\1=***',
            masked
        )
        
        # Mask generic tokens/passwords in environment variables
        masked = re.sub(
            r'(PASSWORD|TOKEN|SECRET|KEY|APIKEY|API_KEY)=\S+',
            r'\1=***',
            masked,
            flags=re.IGNORECASE
        )
        
        return masked

    async def execute_with_logging(
        self,
        command: str,
        project_id: str,
        deployment_id: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> str:
        """Execute command with logging"""
        # Check if deployment was aborted before executing command (without updating DB to prevent thrashing)
        if await self.check_if_aborted(deployment_id, update_db=False):
            raise Exception("Deployment aborted by user")
            
        if deployment_id:
            masked_command = self.mask_sensitive_command(command)
            await self.log_to_database(deployment_id, f"Executing: {masked_command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                error_msg = f"Command failed: {result.stderr}"
                if deployment_id:
                    await self.log_to_database(deployment_id, f"Error: {error_msg}")
                raise Exception(error_msg)

            if deployment_id and result.stdout.strip():
                await self.log_to_database(
                    deployment_id, f"Output: {result.stdout.strip()}"
                )

            return result.stdout
        except subprocess.TimeoutExpired:
            error_msg = "Command timed out"
            if deployment_id:
                await self.log_to_database(deployment_id, f"Error: {error_msg}")
            raise Exception(error_msg)
        except Exception as error:
            if deployment_id:
                await self.log_to_database(deployment_id, f"Error: {str(error)}")
            raise

    async def get_account_id(self) -> str:
        """Get AWS account ID"""
        try:
            response = self.sts.get_caller_identity()
            return response["Account"]
        except Exception as error:
            raise Exception(f"Failed to get AWS account ID: {error}")

    async def get_ecr_registry(self) -> str:
        """Get ECR registry URL"""
        try:
            account_id = await self.get_account_id()
            return f"{account_id}.dkr.ecr.{self.region}.amazonaws.com"
        except Exception as error:
            raise Exception(f"Failed to get ECR registry: {error}")

    async def ensure_ecr_repository(self, repository_name: str) -> None:
        """Ensure ECR repository exists"""
        try:
            # Check if repository exists
            self.ecr.describe_repositories(repositoryNames=[repository_name])
            logger.info(f"ECR repository {repository_name} already exists")
        except self.ecr.exceptions.RepositoryNotFoundException:
            # Repository doesn't exist, create it
            logger.info(f"Creating ECR repository: {repository_name}")

            self.ecr.create_repository(
                repositoryName=repository_name,
                imageScanningConfiguration={"scanOnPush": True},
                encryptionConfiguration={"encryptionType": "AES256"},
            )

            logger.info(f"Created ECR repository: {repository_name}")

    async def deploy_project(
        self, config: DeploymentConfig, deployment_id: Optional[str] = None
    ) -> ECSInfrastructureOutput:
        """Deploy project to AWS infrastructure"""
        clone_dir: Optional[str] = None
        # Store config for use in other methods
        self.config = config

        try:
            # SQLModel doesn't need explicit connection management
                
            # Register deployment for tracking
            if deployment_id:
                deployment_manager.register_deployment(config.project_id, deployment_id)
                await self.log_to_database(
                    deployment_id, "🚀 Starting deployment process..."
                )

            # Step 1: Clone repository
            if deployment_id:
                await self.log_to_database(deployment_id, "📥 Cloning repository...")
            
            # Check if aborted before cloning
            if await self.check_if_aborted(deployment_id):
                raise Exception("Deployment aborted by user")
                
            clone_dir = await self.clone_repository(
                config.git_repo_url,
                config.branch,
                config.commit_sha,
                config.project_id,
                deployment_id,
            )

            # Step 2: Ensure CodeBuild role exists
            if deployment_id:
                await self.log_to_database(
                    deployment_id, "🔐 Ensuring CodeBuild IAM role exists..."
                )
            
            await self.ensure_codebuild_role(config.project_name)
            
            # Step 3: Build and push Docker image
            if deployment_id:
                await self.log_to_database(
                    deployment_id, "🐳 Building and pushing Docker image..."
                )
            
            # Check if aborted before building
            if await self.check_if_aborted(deployment_id):
                raise Exception("Deployment aborted by user")
                
            image_uri = await self.build_and_push_image(
                config.project_name,
                config.commit_sha,
                clone_dir,
                config.project_id,
                deployment_id,
                config.subdirectory,
            )

            # Step 4: Deploy infrastructure using AWS API
            if deployment_id:
                await self.log_to_database(
                    deployment_id, "☁️ Provisioning AWS infrastructure..."
                )
            
            # Check if aborted before infrastructure deployment
            if await self.check_if_aborted(deployment_id):
                raise Exception("Deployment aborted by user")
                
            result = await self.deploy_infrastructure(config, image_uri, deployment_id)

            # Wait for service to become healthy before marking as completed
            if deployment_id:
                await self.log_to_database(
                    deployment_id, "🔄 Waiting for service to become healthy..."
                )

                # Wait for service to be ready
                if config.environment_id:
                    success = await self.wait_for_service_healthy_environment(
                        config.environment_id, deployment_id, max_wait_minutes=15
                    )
                else:
                    # Fallback for project-based deployments
                    success = await self.wait_for_service_healthy(
                        config.project_id, deployment_id, max_wait_minutes=15
                    )

                if success:
                    await self.log_to_database(
                        deployment_id, "✅ Deployment completed successfully!"
                    )

                    # Update deployment and environment status in single transaction
                    async with get_async_session() as session:
                        # Get deployment
                        deployment_result = await session.execute(
                            select(Deployment).where(Deployment.id == deployment_id)
                        )
                        deployment = deployment_result.scalar_one_or_none()
                        
                        if deployment:
                            # Update deployment status
                            deployment.status = DeploymentStatus.SUCCESS
                            deployment.updated_at = datetime.now()
                            session.add(deployment)
                            
                            # Update environment status if deployment has environment
                            if deployment.environment_id:
                                env_result = await session.execute(
                                    select(Environment).where(Environment.id == deployment.environment_id)
                                )
                                environment = env_result.scalar_one_or_none()
                                if environment:
                                    environment.status = "DEPLOYED"
                                    environment.updated_at = datetime.now()
                                    session.add(environment)
                            
                            # Commit all changes in single transaction
                            await session.commit()

                    # Complete deployment tracking
                    deployment_manager.complete_deployment(config.project_id)
                else:
                    await self.log_to_database(
                        deployment_id,
                        "❌ Service failed to become healthy within timeout",
                    )

                    # Update deployment and environment status to failed in single transaction
                    async with get_async_session() as session:
                        deployment_result = await session.execute(
                            select(Deployment).where(Deployment.id == deployment_id)
                        )
                        deployment = deployment_result.scalar_one_or_none()
                        
                        if deployment:
                            # Update deployment status
                            deployment.status = DeploymentStatus.FAILED
                            deployment.updated_at = datetime.now()
                            session.add(deployment)
                            
                            # Update environment status if deployment has environment
                            if deployment.environment_id:
                                env_result = await session.execute(
                                    select(Environment).where(Environment.id == deployment.environment_id)
                                )
                                environment = env_result.scalar_one_or_none()
                                if environment:
                                    environment.status = "FAILED"
                                    environment.updated_at = datetime.now()
                                    session.add(environment)
                            
                            # Commit all changes in single transaction
                            await session.commit()

                    # Complete deployment tracking (even if failed)
                    deployment_manager.complete_deployment(config.project_id)

            return result

        except Exception as error:
            error_message = str(error)
            logger.error(f"Deployment failed: {error}")

            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"❌ Deployment failed: {error_message}"
                )

                # Update deployment status to failed
                async with get_async_session() as session:
                    result = await session.execute(
                        select(Deployment).where(Deployment.id == deployment_id)
                    )
                    deployment = result.scalar_one_or_none()
                    if deployment:
                        deployment.status = DeploymentStatus.FAILED
                        deployment.updated_at = datetime.now()
                        session.add(deployment)
                        await session.commit()

                # Complete deployment tracking (even if failed/aborted)
                deployment_manager.complete_deployment(config.project_id)

                # Update environment status to failed
                async with get_async_session() as env_session:
                    deployment_result = await env_session.execute(
                        select(Deployment).where(Deployment.id == deployment_id)
                    )
                    deployment_obj = deployment_result.scalar_one_or_none()
                    
                    if deployment_obj and deployment_obj.environment_id:
                        env_result = await env_session.execute(
                            select(Environment).where(Environment.id == deployment_obj.environment_id)
                        )
                        environment = env_result.scalar_one_or_none()
                        if environment:
                            environment.status = "FAILED"
                            environment.updated_at = datetime.now()
                            env_session.add(environment)
                            await env_session.commit()

            raise error
        finally:
            # Clean up clone directory
            if clone_dir and os.path.exists(clone_dir):
                try:
                    shutil.rmtree(clone_dir)
                    if deployment_id:
                        await self.log_to_database(
                            deployment_id, "🧹 Cleaned up temporary files"
                        )
                    logger.info(f"Cleaned up clone directory: {clone_dir}")
                except Exception as error:
                    logger.warning(f"Failed to clean up clone directory: {error}")

    async def clone_repository(
        self,
        git_repo_url: str,
        branch: str,
        commit_sha: str,
        project_id: str,
        deployment_id: Optional[str] = None,
    ) -> str:
        """Clone git repository"""
        clone_dir = tempfile.mkdtemp(prefix="clone-")

        try:
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"Cloning repository: {git_repo_url}"
                )

            # Get GitHub access token for the user
            github_token = await self.get_github_token(project_id)

            # Create authenticated clone URL
            authenticated_url = await self.create_authenticated_git_url(
                git_repo_url, github_token
            )

            if deployment_id:
                await self.log_to_database(
                    deployment_id,
                    "Using GitHub authentication for private repository access",
                )

            await self.execute_with_logging(
                f"git clone -b {branch} {authenticated_url} {clone_dir}",
                project_id,
                deployment_id,
            )

            if deployment_id:
                await self.log_to_database(
                    deployment_id,
                    f"Checked out branch: {branch} (commit: {commit_sha})",
                )

            # Check for Dockerfile or buildpack usage
            if deployment_id:
                await self.log_to_database(deployment_id, "Checking build configuration...")

            # Determine the actual build path
            build_path = clone_dir
            if hasattr(self, 'config') and self.config and self.config.subdirectory:
                build_path = os.path.join(clone_dir, self.config.subdirectory)

            use_buildpack = BuildpackService.should_use_buildpack(clone_dir, getattr(self.config, 'subdirectory', None) if hasattr(self, 'config') else None)
            
            if use_buildpack:
                if deployment_id:
                    await self.log_to_database(
                        deployment_id, "📦 No Dockerfile found. Will use Cloud Native Buildpacks for automatic build configuration."
                    )
            else:
                if deployment_id:
                    await self.log_to_database(
                        deployment_id, "✅ Found Dockerfile in repository"
                    )

            return clone_dir

        except Exception as error:
            # Clean up on error
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)
            raise Exception(f"Failed to clone repository: {error}")

    async def get_github_token(self, project_id: str) -> str:
        """Get GitHub access token for project team"""
        try:
            async with get_async_session() as session:
                # Get the project with team
                result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                
                if not project or not project.team_id:
                    raise Exception("Project or team not found")
                
                # Get team with owner
                team_result = await session.execute(
                    select(Team).where(Team.id == project.team_id)
                )
                team = team_result.scalar_one_or_none()
                
                if not team:
                    raise Exception("Team not found")
                
                # First try to get token from team owner
                owner_accounts_result = await session.execute(
                    select(Account).where(
                        (Account.user_id == team.owner_id) & 
                        (Account.provider == "github")
                    )
                )
                owner_account = owner_accounts_result.scalar_one_or_none()
                
                if owner_account and owner_account.access_token:
                    return owner_account.access_token
                
                # If owner doesn't have GitHub token, try team members
                members_result = await session.execute(
                    select(TeamMember).where(TeamMember.team_id == team.id)
                )
                members = members_result.scalars().all()
                
                for member in members:
                    member_accounts_result = await session.execute(
                        select(Account).where(
                            (Account.user_id == member.user_id) & 
                            (Account.provider == "github")
                        )
                    )
                    member_account = member_accounts_result.scalar_one_or_none()
                    
                    if member_account and member_account.access_token:
                        return member_account.access_token
                
                # Fallback to environment variable
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    raise Exception(
                        "GitHub access token not found. Please ensure team owner or members have connected their GitHub account."
                    )
                return token

        except Exception as error:
            raise Exception(f"Failed to get GitHub token: {error}")

    async def create_authenticated_git_url(self, git_repo_url: str, token: str) -> str:
        """Create authenticated Git URL"""
        if "github.com" not in git_repo_url:
            raise Exception("Only GitHub repositories are currently supported")

        # Handle both .git and non-.git URLs
        clean_url = git_repo_url.replace("https://github.com/", "").replace(".git", "")
        return f"https://{token}@github.com/{clean_url}.git"

    async def build_and_push_image(
        self,
        project_name: str,
        commit_sha: str,
        clone_dir: str,
        project_id: str,
        deployment_id: Optional[str] = None,
        subdirectory: Optional[str] = None,
    ) -> str:
        """Build and push Docker image to ECR"""
        ecr_registry = await self.get_ecr_registry()
        repository_name = project_name.lower().replace("[^a-z0-9-_]", "-")
        image_tag = f"{repository_name}:{commit_sha}"
        image_uri = f"{ecr_registry}/{image_tag}"

        try:
            # Ensure ECR repository exists
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"Ensuring ECR repository exists: {repository_name}"
                )
            await self.ensure_ecr_repository(repository_name)

            # Start CodeBuild project to build and push image
            if deployment_id:
                await self.log_to_database(
                    deployment_id, "Starting CodeBuild project for container build..."
                )
                if subdirectory:
                    await self.log_to_database(
                        deployment_id, f"📁 Build context: subdirectory '{subdirectory}'"
                    )

            build_id = await self.start_codebuild(
                project_name,
                repository_name,
                commit_sha,
                clone_dir,
                project_id,
                deployment_id,
                subdirectory,
            )

            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"CodeBuild started: {build_id}"
                )

            # Wait for build to complete
            await self.wait_for_codebuild_completion(build_id, deployment_id)

            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"✅ Successfully built and pushed image: {image_uri}"
                )

            return image_uri
        except Exception as error:
            raise Exception(f"Failed to build/push image: {error}")

    async def start_codebuild(
        self,
        project_name: str,
        repository_name: str,
        commit_sha: str,
        clone_dir: str,
        project_id: str,
        deployment_id: Optional[str] = None,
        subdirectory: Optional[str] = None,
    ) -> str:
        """Start CodeBuild project"""
        # Get environment variables for the specific environment (not project)
        environment_variables = []
        if hasattr(self, 'config') and self.config.environment_id:
            environment_variables = await self.get_environment_variables_for_environment(self.config.environment_id)
        else:
            # Fallback to project variables if no environment specified
            environment_variables = await self.get_environment_variables(project_id)
        
        # Create .env file in .autoform directory with all non-secret environment variables
        if environment_variables:
            # Create .autoform directory if it doesn't exist
            autoform_dir = os.path.join(clone_dir, ".autoform")
            os.makedirs(autoform_dir, exist_ok=True)
            
            env_file_path = os.path.join(autoform_dir, ".env")
            env_content = []
            
            for env_var in environment_variables:
                # Only include non-secret variables with values
                if env_var.value and not env_var.is_secret:
                    # Format as KEY=VALUE for .env file
                    env_content.append(f"{env_var.key}={env_var.value}")
            
            if env_content:
                with open(env_file_path, "w") as env_file:
                    env_file.write("\n".join(env_content))
                    env_file.write("\n")  # Add trailing newline
                
                if deployment_id:
                    await self.log_to_database(
                        deployment_id, 
                        f"📄 Created .autoform/.env file with {len(env_content)} environment variable(s)"
                    )
        
        # Upload source to S3 (now including the .env file)
        source_location = await self.upload_source_to_s3(
            clone_dir, project_name, commit_sha
        )

        build_project_name = f"{re.sub(r'[^a-z0-9-]', '-', project_name.lower())}-build"

        # Get environment variables again for build args (if needed for Docker build args)
        environment_variables = await self.get_environment_variables(project_id)

        # Build docker build args from environment variables
        build_args = ""
        if environment_variables:
            for env_var in environment_variables:
                if env_var.value:  # Only non-secret vars with values
                    # Escape single quotes in the value
                    escaped_value = env_var.value.replace("'", "'\"'\"'")
                    build_args += f" --build-arg {env_var.key}='{escaped_value}'"

        # Add leading space if build_args is not empty
        if build_args:
            build_args = " " + build_args.strip()

        # Debug: Log the build args
        print(f"Build args: '{build_args}'")

        # Check if we should use buildpack
        use_buildpack = BuildpackService.should_use_buildpack(clone_dir, subdirectory)
        
        # Get builder - always use Google Cloud buildpacks
        builder = BuildpackService.get_builder()

        # Create buildspec content
        ecr_registry = await self.get_ecr_registry()
        account_id = await self.get_account_id()

        # Build the buildspec as a proper YAML structure
        if use_buildpack:
            # Buildpack-based build
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"🏗️ Using Cloud Native Buildpack builder: {builder}"
                )
            
            buildspec_content = f"""version: 0.2
phases:
  install:
    runtime-versions:
      docker: 20
    commands:
      - echo Installing pack CLI...
      - |
        curl -sSL "https://github.com/buildpacks/pack/releases/download/v0.33.2/pack-v0.33.2-linux.tgz" | tar -C /usr/local/bin/ --no-same-owner -xzv pack
      - pack version
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {ecr_registry}
      - echo Checking for Docker Hub credentials...
      - |
        if aws secretsmanager describe-secret --secret-id dockerhub-credentials --region {self.region} >/dev/null 2>&1; then
          echo "Docker Hub credentials found, logging in..."
          DOCKERHUB_USERNAME=$(aws secretsmanager get-secret-value --secret-id dockerhub-credentials --region {self.region} --query SecretString --output text | jq -r .username)
          DOCKERHUB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id dockerhub-credentials --region {self.region} --query SecretString --output text | jq -r .password)
          echo "$DOCKERHUB_PASSWORD" | docker login --username "$DOCKERHUB_USERNAME" --password-stdin
          echo "Docker Hub login successful"
        else
          echo "No Docker Hub credentials found, proceeding without authentication"
        fi"""
        else:
            # Dockerfile-based build
            buildspec_content = f"""version: 0.2
phases:
  pre_build:
    commands:
      - echo Logging in to Docker Hub...
      - |
        if [ ! -z "$DOCKERHUB_USERNAME" ] && [ ! -z "$DOCKERHUB_PASSWORD" ]; then
          echo "Docker Hub credentials provided, logging in..."
          echo "$DOCKERHUB_PASSWORD" | docker login --username "$DOCKERHUB_USERNAME" --password-stdin >/dev/null 2>&1
          if [ $? -eq 0 ]; then
            echo "Docker Hub login successful"
          else
            echo "Docker Hub login failed, proceeding without authentication"
          fi
        else
          echo "No Docker Hub credentials provided, proceeding without authentication"
        fi
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {ecr_registry}"""

        if subdirectory:
            buildspec_content += f"""
      - echo Changing to subdirectory {subdirectory}
      - cd {subdirectory}"""

        if use_buildpack:
            # Convert build args to pack env format
            pack_env_args = ""
            if environment_variables:
                for env_var in environment_variables:
                    if env_var.value:  # Only non-secret vars with values
                        # Escape single quotes in the value
                        escaped_value = env_var.value.replace("'", "'\"'\"'")
                        pack_env_args += f" --env {env_var.key}='{escaped_value}'"
            
            # Add buildpack-specific env vars
            buildpack_env = BuildpackService.get_pack_build_command(
                f"{ecr_registry}/{repository_name}:{commit_sha}",
                builder,
                ".",
                {}  # We'll handle env vars separately
            )
            
            buildspec_content += f"""
  build:
    commands:
      - echo Build started on `date`
      - echo Building with Cloud Native Buildpack...
      - |
        # Pull builder image for cache
        docker pull {builder} || echo "Could not pull builder image"
      - |
        # Build with pack
        pack build {ecr_registry}/{repository_name}:{commit_sha} \\
          --builder {builder} \\
          --trust-builder \\
          --publish{pack_env_args}
      - |
        # Also tag as latest
        docker pull {ecr_registry}/{repository_name}:{commit_sha}
        docker tag {ecr_registry}/{repository_name}:{commit_sha} {ecr_registry}/{repository_name}:latest
        docker push {ecr_registry}/{repository_name}:latest
  post_build:
    commands:
      - echo Build completed on `date`
      - echo Image published to {ecr_registry}/{repository_name}:{commit_sha}"""
        else:
            # Dockerfile build
            buildspec_content += f"""
  build:
    commands:
      - echo Build started on `date`
      - echo Building the Docker image with cache...
      - |
        # Try to pull the latest image for cache
        docker pull {ecr_registry}/{repository_name}:latest || echo "No previous image found for cache"
      - docker build{build_args} --cache-from {ecr_registry}/{repository_name}:latest -t {repository_name}:{commit_sha} -t {repository_name}:latest .
      - docker tag {repository_name}:{commit_sha} {ecr_registry}/{repository_name}:{commit_sha}
      - docker tag {repository_name}:latest {ecr_registry}/{repository_name}:latest
  post_build:
    commands:
      - echo Build completed on `date`
      - echo Pushing the Docker images...
      - docker push {ecr_registry}/{repository_name}:{commit_sha}
      - docker push {ecr_registry}/{repository_name}:latest"""

        buildspec = buildspec_content

        # Debug: Log the generated buildspec
        print("Generated buildspec.yml:")
        print(buildspec)
        print("=" * 50)

        log_group_name = f"/aws/codebuild/{build_project_name}"

        # Ensure CloudWatch log group exists
        try:
            self.cloudwatch_logs.create_log_group(logGroupName=log_group_name)
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"Created CloudWatch log group: {log_group_name}"
                )
        except self.cloudwatch_logs.exceptions.ResourceAlreadyExistsException:
            pass  # Log group already exists
        except Exception as error:
            logger.warning(f"Failed to create log group: {error}")

        params = {
            "name": build_project_name,
            "source": {
                "type": "S3",
                "location": source_location,
                "buildspec": buildspec,
            },
            "artifacts": {"type": "NO_ARTIFACTS"},
            "environment": {
                "type": "LINUX_CONTAINER",
                "image": "aws/codebuild/amazonlinux2-x86_64-standard:4.0",
                "computeType": "BUILD_GENERAL1_SMALL",
                "privilegedMode": True,
                "environmentVariables": await self._get_codebuild_env_vars(),
            },
            "cache": {"type": "LOCAL", "modes": ["LOCAL_DOCKER_LAYER_CACHE"]},
            "logsConfig": {
                "cloudWatchLogs": {"status": "ENABLED", "groupName": log_group_name}
            },
            "serviceRole": await self.get_codebuild_role(project_name),
        }

        # Create or update CodeBuild project
        try:
            self.codebuild.create_project(**params)
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"Created CodeBuild project: {build_project_name}"
                )
        except self.codebuild.exceptions.ResourceAlreadyExistsException:
            # Update existing project
            self.codebuild.update_project(**params)
            if deployment_id:
                await self.log_to_database(
                    deployment_id, f"Updated CodeBuild project: {build_project_name}"
                )

        # Start build
        result = self.codebuild.start_build(projectName=build_project_name)

        return result["build"]["id"]

    async def wait_for_codebuild_completion(
        self, build_id: str, deployment_id: Optional[str] = None
    ):
        """Wait for CodeBuild to complete"""
        log_group_name: Optional[str] = None
        log_stream_name: Optional[str] = None
        next_token: Optional[str] = None
        log_stream_found = False

        # Add timeout protection
        start_time = time.time()
        MAX_WAIT_SECONDS = 30 * 60  # 30 minutes maximum

        while True:
            # Check if deployment was aborted (without updating DB to prevent thrashing in the build loop)
            if await self.check_if_aborted(deployment_id, update_db=False):
                raise Exception("Deployment aborted by user")
            
            # Check timeout
            elapsed_time = time.time() - start_time
            if elapsed_time > MAX_WAIT_SECONDS:
                error_msg = f"CodeBuild timeout after {MAX_WAIT_SECONDS // 60} minutes"
                if deployment_id:
                    await self.log_to_database(deployment_id, f"❌ {error_msg}")
                raise TimeoutError(error_msg)
            result = self.codebuild.batch_get_builds(ids=[build_id])
            build = result["builds"][0]
            status = build["buildStatus"]

            # Get log info if available
            if build.get("logs") and not log_stream_found:
                # Debug: log the entire logs structure
                logs_data = build.get("logs", {})

                # Check different possible structures
                # Sometimes it's logs.cloudWatchLogs, sometimes logs.cloudWatchLogsArn contains the info
                cloud_watch_logs = logs_data.get("cloudWatchLogs", {})
                cloud_watch_logs_arn = logs_data.get("cloudWatchLogsArn", "")

                # Try to extract from ARN if direct fields are not available
                if cloud_watch_logs_arn and "null" not in cloud_watch_logs_arn:
                    # ARN format: arn:aws:logs:region:account:log-group:/aws/codebuild/project:log-stream:stream-name
                    arn_parts = cloud_watch_logs_arn.split(":")
                    if len(arn_parts) >= 7:
                        log_group_part = arn_parts[
                            6
                        ]  # log-group:/aws/codebuild/project
                        if log_group_part.startswith("log-group:"):
                            log_group_name = log_group_part.replace("log-group:", "")
                        if len(arn_parts) >= 9 and arn_parts[7] == "log-stream":
                            log_stream_name = arn_parts[8]

                # Fallback to direct fields if available
                if not log_group_name and cloud_watch_logs.get("groupName"):
                    log_group_name = cloud_watch_logs["groupName"]
                if not log_stream_name and cloud_watch_logs.get("streamName"):
                    log_stream_name = cloud_watch_logs.get("streamName")

                # Only mark as found if we have both group and stream
                if log_group_name and log_stream_name:
                    log_stream_found = True

            # Stream logs if available
            if log_group_name and log_stream_name and deployment_id:
                try:
                    # Prepare parameters for get_log_events
                    params = {
                        "logGroupName": log_group_name,
                        "logStreamName": log_stream_name,
                        "startFromHead": True,
                    }

                    # Only add nextToken if it exists and is not None
                    if next_token:
                        params["nextToken"] = next_token

                    logs_result = self.cloudwatch_logs.get_log_events(**params)

                    events = logs_result.get("events", [])

                    for event in events:
                        if event.get("message") and event["message"].strip():
                            await self.log_to_database(
                                deployment_id, f"🔨 {event['message'].strip()}"
                            )

                    # Update nextToken for next iteration
                    new_next_token = logs_result.get("nextForwardToken")
                    if new_next_token != next_token:  # Only update if it's different
                        next_token = new_next_token

                except Exception as error:
                    if deployment_id:
                        await self.log_to_database(
                            deployment_id, f"❌ Log streaming error: {str(error)}"
                        )
                    logger.warning(f"Failed to stream logs: {error}")

            if deployment_id:
                # Only log status changes
                if (
                    not hasattr(self, "_last_build_status")
                    or self._last_build_status != status
                ):
                    await self.log_to_database(
                        deployment_id, f"CodeBuild status: {status}"
                    )
                    self._last_build_status = status

            if status == "SUCCEEDED":
                # Get final logs
                if log_group_name and log_stream_name and deployment_id:
                    try:
                        final_logs = self.cloudwatch_logs.get_log_events(
                            logGroupName=log_group_name,
                            logStreamName=log_stream_name,
                            nextToken=next_token,
                            startFromHead=True,
                        )

                        for event in final_logs.get("events", []):
                            if event.get("message"):
                                await self.log_to_database(
                                    deployment_id, f"🔨 {event['message'].strip()}"
                                )
                    except Exception as error:
                        logger.warning(f"Failed to get final logs: {error}")
                return
            elif status in ["FAILED", "FAULT", "STOPPED", "TIMED_OUT"]:
                if log_group_name and deployment_id:
                    await self.log_to_database(
                        deployment_id,
                        f"❌ CodeBuild logs available in CloudWatch: {log_group_name}",
                    )
                raise Exception(f"CodeBuild failed with status: {status}")

            # Wait 5 seconds before checking again
            time.sleep(5)

    async def upload_source_to_s3(
        self, clone_dir: str, project_name: str, commit_sha: str
    ) -> str:
        """Upload source code to S3"""
        bucket_name = (
            f"{project_name.lower().replace('[^a-z0-9-]', '-')}-builds-{self.region}"
        )
        key_name = f"source/{commit_sha}.zip"

        # Create bucket if it doesn't exist
        try:
            if self.region == "us-east-1":
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": self.region},
                )
        except self.s3.exceptions.BucketAlreadyOwnedByYou:
            pass  # Bucket already exists
        except self.s3.exceptions.BucketAlreadyExists:
            pass  # Bucket already exists

        # Create zip of source code using Python
        import zipfile
        import os

        zip_path = f"/tmp/{commit_sha}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(clone_dir):
                # Skip .git directories
                dirs[:] = [d for d in dirs if not d.startswith(".git")]

                for file in files:
                    # Skip .git files
                    if ".git" in file:
                        continue

                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, clone_dir)
                    zipf.write(file_path, arc_name)

        # Upload to S3 using put_object for better error handling
        with open(zip_path, "rb") as f:
            file_content = f.read()
            self.s3.put_object(
                Bucket=bucket_name,
                Key=key_name,
                Body=file_content
            )

        # Clean up local zip
        os.remove(zip_path)

        return f"{bucket_name}/{key_name}"

    async def ensure_codebuild_role(self, project_name: str) -> str:
        """Ensure CodeBuild service role exists and return its ARN"""
        from infrastructure.services.iam_service import IAMService
        
        # Create IAM service to ensure role exists
        iam_service = IAMService(
            project_name=project_name,
            region=self.region,
            aws_credentials=self.aws_credentials
        )
        
        # This will create the CodeBuild role if it doesn't exist
        await iam_service._create_codebuild_role()
        
        return iam_service.codebuild_role_arn
    
    async def get_codebuild_role(self, project_name: str) -> str:
        """Get CodeBuild service role ARN"""
        response = self.sts.get_caller_identity()
        account_id = response["Account"]
        # Use the same role naming convention as iam_service.py
        return f"arn:aws:iam::{account_id}:role/{project_name}-codebuild-role"

    async def deploy_infrastructure(
        self,
        config: DeploymentConfig,
        image_uri: str,
        deployment_id: Optional[str] = None,
    ) -> ECSInfrastructureOutput:
        """Deploy AWS infrastructure"""
        # Fetch environment variables for the project
        environment_variables = await self.get_environment_variables(config.project_id)

        if deployment_id and environment_variables:
            await self.log_to_database(
                deployment_id,
                f"📋 Found {len(environment_variables)} environment variables",
            )

        # Fetch environment to get network configuration (for existing VPC/subnets/cluster only)
        if config.environment_id:
            if deployment_id:
                await self.log_to_database(deployment_id, "🔍 Fetching environment network configuration...")
            environment_network = await self.get_environment_network_config(config.environment_id)
        else:
            # Fallback to project configuration for backward compatibility
            if deployment_id:
                await self.log_to_database(deployment_id, "🔍 Fetching project network configuration...")
            environment_network = await self.get_project_network_config(config.project_id)

        infrastructure_args = ECSInfrastructureArgs(
            project_name=config.project_name,
            image_uri=image_uri,
            container_port=config.port,
            health_check_path=config.health_check_path,
            region=self.region,
            environment_variables=environment_variables,
            cpu=config.cpu,
            memory=config.memory,
            disk_size=config.disk_size,
            existing_vpc_id=environment_network.get("existing_vpc_id"),
            existing_subnet_ids=environment_network.get("existing_subnet_ids"),
            existing_cluster_arn=environment_network.get("existing_cluster_arn"),
            domain_name=environment_network.get("domain"),
            certificate_arn=environment_network.get("certificate_arn"),
            auto_provision_certificate=environment_network.get("auto_provision_certificate", True),
            use_route53_validation=environment_network.get("use_route53_validation", True),
            redirect_http_to_https=True,
            desired_instance_count=config.desired_instance_count,
        )

        # Add existing network resources if configured
        if environment_network.get("existing_vpc_id"):
            if deployment_id:
                await self.log_to_database(
                    deployment_id,
                    f"🌐 Using existing VPC: {environment_network['existing_vpc_id']}",
                )

        if environment_network.get("existing_subnet_ids"):
            if deployment_id:
                subnet_list = ", ".join(environment_network["existing_subnet_ids"])
                await self.log_to_database(
                    deployment_id, f"🌐 Using existing subnets: {subnet_list}"
                )

        if environment_network.get("existing_cluster_arn"):
            if deployment_id:
                await self.log_to_database(
                    deployment_id,
                    f"🚀 Using existing ECS cluster: {environment_network['existing_cluster_arn']}",
                )

        infrastructure = ECSInfrastructure(
            infrastructure_args, aws_credentials=self.aws_credentials
        )

        if deployment_id:
            await self.log_to_database(
                deployment_id, "Creating/updating AWS infrastructure..."
            )
            await self.log_to_database(
                deployment_id,
                f"- Resource allocation: {config.cpu} CPU units, "
                f"{config.memory} MB memory, {config.disk_size} GB disk",
            )
            await self.log_to_database(deployment_id, "- Setting up VPC and networking")
            await self.log_to_database(deployment_id, "- Creating security groups")
            await self.log_to_database(
                deployment_id, "- Setting up ECS cluster and service"
            )
            await self.log_to_database(deployment_id, "- Configuring load balancer")
            if environment_variables:
                await self.log_to_database(
                    deployment_id,
                    f"- Configuring {len(environment_variables)} environment variables and secrets",
                )

        result = await infrastructure.create_or_update_infrastructure()

        if deployment_id:
            await self.log_to_database(deployment_id, "✅ Infrastructure ready!")
            await self.log_to_database(
                deployment_id, f"- ECS Service: {result.service_arn}"
            )
            await self.log_to_database(
                deployment_id, f"- Load Balancer: {result.load_balancer_dns}"
            )

        # Update environment with deployed resource ARNs and network info
        environment_update_data = {}
        if result.service_arn:
            environment_update_data["ecsServiceArn"] = result.service_arn
        if result.cluster_arn:
            environment_update_data["ecsClusterArn"] = result.cluster_arn
        if result.load_balancer_arn:
            environment_update_data["albArn"] = result.load_balancer_arn
        if result.load_balancer_dns:
            # Always store ALB DNS in domain field
            environment_update_data["domain"] = result.load_balancer_dns
        if result.certificate_arn:
            environment_update_data["certificate_arn"] = result.certificate_arn
        if result.vpc_id and not environment_network.get("existing_vpc_id"):
            # Only update VPC if it wasn't using an existing one
            environment_update_data["existingVpcId"] = result.vpc_id
        if result.subnet_ids and not environment_network.get("existing_subnet_ids"):
            # Only update subnets if it wasn't using existing ones
            import json
            environment_update_data["existingSubnetIds"] = json.dumps(result.subnet_ids)

        if environment_update_data and config.environment_id:
            async with get_async_session() as session:
                result = await session.execute(
                    select(Environment).where(Environment.id == config.environment_id)
                )
                environment = result.scalar_one_or_none()
                if environment:
                    # Map the legacy field names to SQLModel field names
                    field_mapping = {
                        'ecsServiceArn': 'ecs_service_arn',
                        'ecsClusterArn': 'ecs_cluster_arn',
                        'albArn': 'alb_arn',
                        'existingVpcId': 'existing_vpc_id',
                        'existingSubnetIds': 'existing_subnet_ids',
                        'domain': 'domain'
                    }
                    
                    for key, value in environment_update_data.items():
                        sqlmodel_field = field_mapping.get(key, key)
                        setattr(environment, sqlmodel_field, value)
                    environment.updated_at = datetime.now()
                    session.add(environment)
                    await session.commit()

        return result

    async def wait_for_service_healthy_environment(
        self, environment_id: str, deployment_id: str, max_wait_minutes: int = 15
    ) -> bool:
        """Wait for ECS service to become healthy using environment data"""
        import boto3
        import asyncio
        from botocore.exceptions import ClientError

        # Track logged events to avoid duplicates
        logged_events = set()

        try:
            # Get environment details
            async with get_async_session() as session:
                result = await session.execute(
                    select(Environment).where(Environment.id == environment_id)
                )
                environment = result.scalar_one_or_none()
                
                if not environment or not environment.ecs_service_arn or not environment.ecs_cluster_arn:
                    await self.log_to_database(
                        deployment_id, "❌ Missing ECS service or cluster information in environment"
                    )
                    return False

            # Use the same credentials as the deployment service
            client_config = {"region_name": self.region}
            if self.aws_credentials:
                client_config.update(
                    {
                        "aws_access_key_id": self.aws_credentials["access_key"],
                        "aws_secret_access_key": self.aws_credentials["secret_key"],
                    }
                )

            ecs_client = create_client("ecs", client_config["region_name"], self.aws_credentials)

            cluster_arn = environment.ecs_cluster_arn
            service_arn = environment.ecs_service_arn

            start_time = asyncio.get_event_loop().time()
            max_wait_seconds = max_wait_minutes * 60
            check_interval = 30  # Check every 30 seconds

            await self.log_to_database(
                deployment_id,
                f"Monitoring service health for up to {max_wait_minutes} minutes...",
            )

            while True:
                # Check if deployment was aborted (without updating DB to prevent thrashing in the wait loop)
                if await self.check_if_aborted(deployment_id, update_db=False):
                    return False
                    
                elapsed = asyncio.get_event_loop().time() - start_time

                if elapsed > max_wait_seconds:
                    await self.log_to_database(
                        deployment_id, f"⏰ Timeout after {max_wait_minutes} minutes"
                    )
                    return False

                try:
                    # Extract service name from ARN if it's an ARN
                    service_identifier = service_arn
                    if service_arn.startswith("arn:aws:ecs:"):
                        service_identifier = service_arn.split("/")[-1]

                    # Extract cluster name from ARN if it's an ARN
                    cluster_identifier = cluster_arn
                    if cluster_arn.startswith("arn:aws:ecs:"):
                        cluster_identifier = cluster_arn.split("/")[-1]

                    # Check service status
                    response = ecs_client.describe_services(
                        cluster=cluster_identifier, services=[service_identifier]
                    )

                    if not response["services"]:
                        await self.log_to_database(deployment_id, "❌ Service not found")
                        return False

                    service = response["services"][0]

                    # Get service metrics
                    service_status = service["status"]
                    running_count = service.get("runningCount", 0)
                    desired_count = service.get("desiredCount", 0)
                    pending_count = service.get("pendingCount", 0)

                    # Check deployment status
                    deployments = service.get("deployments", [])
                    primary_deployment = None
                    for deployment in deployments:
                        if deployment["status"] == "PRIMARY":
                            primary_deployment = deployment
                            break

                    deployment_stable = False
                    if primary_deployment:
                        rollout_state = primary_deployment.get("rolloutState", "")
                        deployment_running = primary_deployment.get("runningCount", 0)
                        deployment_desired = primary_deployment.get("desiredCount", 0)

                        deployment_stable = (
                            rollout_state == "COMPLETED"
                            and deployment_running == deployment_desired
                            and deployment_desired > 0
                        )

                    # Service is healthy if:
                    # 1. Service is ACTIVE
                    # 2. Running count matches desired count
                    # 3. No pending tasks
                    # 4. Primary deployment is stable
                    is_healthy = (
                        service_status == "ACTIVE"
                        and running_count == desired_count
                        and desired_count > 0
                        and pending_count == 0
                        and deployment_stable
                    )

                    await self.log_to_database(
                        deployment_id,
                        f"📊 Service status: {service_status}, "
                        f"Running: {running_count}/{desired_count}, "
                        f"Pending: {pending_count}, "
                        f"Deployment stable: {deployment_stable}",
                    )

                    # Log recent ECS service events (helpful for debugging deployment issues)
                    events = service.get("events", [])[:3]  # Get last 3 events
                    for event in events:
                        event_message = event.get("message", "")
                        event_id = event.get("id", "")
                        
                        # Only log events we haven't seen before
                        if event_message and event_id and event_id not in logged_events:
                            logged_events.add(event_id)
                            await self.log_to_database(
                                deployment_id,
                                f"ECS Event: {event_message}",
                            )

                    if is_healthy:
                        await self.log_to_database(
                            deployment_id, "✅ Service is healthy and ready!"
                        )
                        return True

                    # Check if we should abort
                    from services.deployment_manager import deployment_manager
                    if deployment_manager.is_deployment_aborted(deployment_id):
                        await self.log_to_database(
                            deployment_id, "🛑 Health check aborted by user"
                        )
                        return False

                    # Wait before next check
                    await asyncio.sleep(check_interval)

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    await self.log_to_database(
                        deployment_id, f"❌ AWS Error checking service health: {error_code}"
                    )
                    return False
                except Exception as e:
                    await self.log_to_database(
                        deployment_id, f"❌ Error monitoring service health: {e}"
                    )
                    return False

        except Exception as error:
            await self.log_to_database(
                deployment_id, f"❌ Failed to monitor service health: {error}"
            )
            return False

    async def wait_for_service_healthy(
        self, project_id: str, deployment_id: str, max_wait_minutes: int = 15
    ) -> bool:
        """Wait for ECS service to become healthy"""
        import boto3
        import asyncio
        from botocore.exceptions import ClientError

        try:
            # Get project details
            async with get_async_session() as session:
                result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()
                
                if not project or not project.ecs_service_arn or not project.ecs_cluster_arn:
                    await self.log_to_database(
                        deployment_id, "❌ Missing ECS service or cluster information"
                    )
                    return False

            # Use the same credentials as the deployment service
            client_config = {
                "region_name": self.region
            }  # Use self.region instead of parameter
            if self.aws_credentials:
                client_config.update(
                    {
                        "aws_access_key_id": self.aws_credentials["access_key"],
                        "aws_secret_access_key": self.aws_credentials["secret_key"],
                    }
                )

            ecs_client = create_client("ecs", client_config["region_name"], self.aws_credentials)

            cluster_arn = project.ecs_cluster_arn
            service_arn = project.ecs_service_arn

            start_time = asyncio.get_event_loop().time()
            max_wait_seconds = max_wait_minutes * 60
            check_interval = 30  # Check every 30 seconds

            await self.log_to_database(
                deployment_id,
                f"Monitoring service health for up to {max_wait_minutes} minutes...",
            )

            while True:
                elapsed = asyncio.get_event_loop().time() - start_time

                if elapsed > max_wait_seconds:
                    await self.log_to_database(
                        deployment_id, f"⏰ Timeout after {max_wait_minutes} minutes"
                    )
                    return False

                try:
                    # Extract service name from ARN if it's an ARN
                    service_identifier = service_arn
                    if service_arn.startswith("arn:aws:ecs:"):
                        service_identifier = service_arn.split("/")[-1]

                    # Extract cluster name from ARN if it's an ARN
                    cluster_identifier = cluster_arn
                    if cluster_arn.startswith("arn:aws:ecs:"):
                        cluster_identifier = cluster_arn.split("/")[-1]

                    # Check service status
                    response = ecs_client.describe_services(
                        cluster=cluster_identifier, services=[service_identifier]
                    )

                    if not response["services"]:
                        await self.log_to_database(deployment_id, "❌ Service not found")
                        return False

                    service = response["services"][0]

                    # Get service metrics
                    service_status = service["status"]
                    running_count = service.get("runningCount", 0)
                    desired_count = service.get("desiredCount", 0)
                    pending_count = service.get("pendingCount", 0)

                    # Check deployment status
                    deployments = service.get("deployments", [])
                    primary_deployment = None
                    for deployment in deployments:
                        if deployment["status"] == "PRIMARY":
                            primary_deployment = deployment
                            break

                    deployment_stable = False
                    if primary_deployment:
                        rollout_state = primary_deployment.get("rolloutState", "")
                        deployment_running = primary_deployment.get("runningCount", 0)
                        deployment_desired = primary_deployment.get("desiredCount", 0)
                        deployment_stable = (
                            rollout_state == "COMPLETED"
                            and deployment_running == deployment_desired
                        )

                    # Check if service is healthy
                    service_healthy = (
                        service_status == "ACTIVE"
                        and running_count == desired_count
                        and running_count > 0
                        and pending_count == 0
                        and deployment_stable
                    )

                    if service_healthy:
                        await self.log_to_database(
                            deployment_id,
                            f"✅ Service is healthy! {running_count}/{desired_count} tasks running",
                        )
                        return True
                    else:
                        # Log current status
                        status_msg = (
                            f"Service status: {running_count}/{desired_count} running"
                        )
                        if pending_count > 0:
                            status_msg += f", {pending_count} pending"
                        if primary_deployment:
                            status_msg += f", rollout: {primary_deployment.get('rolloutState', 'unknown')}"

                        await self.log_to_database(deployment_id, f"🔄 {status_msg}")

                        # Check for failures in recent events
                        events = service.get("events", [])[:5]
                        for event in events:
                            message = event.get("message", "").lower()
                            if any(
                                keyword in message
                                for keyword in ["failed", "stopped", "unhealthy"]
                            ):
                                await self.log_to_database(
                                    deployment_id,
                                    f"⚠️ Service event: {event.get('message', '')}",
                                )

                except ClientError as e:
                    await self.log_to_database(
                        deployment_id, f"❌ Error checking service: {e}"
                    )
                    return False

                # Wait before next check
                await asyncio.sleep(check_interval)

        except Exception as e:
            await self.log_to_database(
                deployment_id, f"❌ Error monitoring service health: {e}"
            )
            return False

    async def get_environment_variables(
        self, project_id: str
    ) -> List[EnvironmentVariable]:
        """Get environment variables for project"""
        try:
            from models.environment import EnvironmentVariable as EnvVarModel
            
            async with get_async_session() as session:
                result = await session.execute(
                    select(EnvVarModel).where(EnvVarModel.project_id == project_id)
                )
                env_vars = result.scalars().all()

                return [
                    EnvironmentVariable(
                        key=env_var.key,
                        value=env_var.value if not env_var.is_secret else None,
                        is_secret=env_var.is_secret,
                        secret_key=env_var.secret_key if env_var.is_secret else None,
                    )
                    for env_var in env_vars
                ]
        except Exception as error:
            logger.error(f"Error fetching environment variables: {error}")
            return []

    async def get_environment_variables_for_environment(
        self, environment_id: str
    ) -> List[EnvironmentVariable]:
        """Get environment variables for a specific environment"""
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(EnvVarModel).where(EnvVarModel.environment_id == environment_id)
                )
                env_vars = result.scalars().all()

                return [
                    EnvironmentVariable(
                        key=env_var.key,
                        value=env_var.value if not env_var.is_secret else None,
                        is_secret=env_var.is_secret,
                        secret_key=env_var.secret_key if env_var.is_secret else None,
                    )
                    for env_var in env_vars
                ]
        except Exception as error:
            logger.error(f"Error fetching environment variables for environment: {error}")
            return []

    async def get_environment_network_config(self, environment_id: str) -> Dict:
        """Get environment network configuration"""
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(Environment).where(Environment.id == environment_id)
                )
                environment = result.scalar_one_or_none()
                
                if not environment:
                    return {
                        "existing_vpc_id": None,
                        "existing_subnet_ids": None,
                        "existing_cluster_arn": None,
                        "cpu": 256,
                        "memory": 512,
                        "disk_size": 21,
                        "port": 3000,
                        "health_check_path": "/",
                    }
                
                # Get the associated project
                project_result = await session.execute(
                    select(Project).where(Project.id == environment.project_id)
                )
                project = project_result.scalar_one_or_none()

                # Parse existing subnet IDs if they exist
                existing_subnet_ids = None
                if environment.existing_subnet_ids:
                    logger.info(f"🔍 Raw subnet IDs from DB: '{environment.existing_subnet_ids}' (type: {type(environment.existing_subnet_ids)})")
                    try:
                        existing_subnet_ids = json.loads(environment.existing_subnet_ids)
                        logger.info(f"✅ Parsed subnet IDs successfully: {existing_subnet_ids}")
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"❌ Failed to parse existing subnet IDs: '{environment.existing_subnet_ids}' - Error: {e}"
                        )

                logger.info(f"🌐 Network config result: VPC='{environment.existing_vpc_id}', Subnets={existing_subnet_ids}")
                return {
                    "existing_vpc_id": environment.existing_vpc_id,
                    "existing_subnet_ids": existing_subnet_ids,
                    "existing_cluster_arn": environment.existing_cluster_arn,
                    "cpu": environment.cpu or 256,
                    "memory": environment.memory or 512,
                    "disk_size": environment.disk_size or 21,
                    "port": project.port if project else 3000,
                    "health_check_path": project.health_check_path if project else "/",
                    "domain": environment.domain,
                    "certificate_arn": environment.certificate_arn,
                    "auto_provision_certificate": environment.auto_provision_certificate,
                    "use_route53_validation": environment.use_route53_validation,
                }
        except Exception as error:
            logger.error(f"Error fetching environment configuration: {error}")
            raise Exception(f"Failed to fetch environment configuration: {error}. Cannot proceed with deployment.")

    async def get_project_network_config(self, project_id: str) -> Dict:
        """Get project network configuration (deprecated - use get_environment_network_config)"""
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = result.scalar_one_or_none()

                if not project:
                    return {
                        "existing_vpc_id": None,
                        "existing_subnet_ids": None,
                        "existing_cluster_arn": None,
                        "cpu": 256,
                        "memory": 512,
                        "disk_size": 21,
                        "port": 3000,
                        "health_check_path": "/",
                    }

                # Parse existing subnet IDs if they exist
                existing_subnet_ids = None
                if project.existing_subnet_ids:
                    try:
                        existing_subnet_ids = json.loads(project.existing_subnet_ids)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Failed to parse existing subnet IDs: {project.existing_subnet_ids}"
                        )

                return {
                    "existing_vpc_id": project.existing_vpc_id,
                    "existing_subnet_ids": existing_subnet_ids,
                    "existing_cluster_arn": project.existing_cluster_arn,
                    "cpu": project.cpu or 256,
                    "memory": project.memory or 512,
                    "disk_size": project.disk_size or 21,
                    "port": project.port or 3000,
                    "health_check_path": project.health_check_path or "/",
                }
        except Exception as error:
            logger.error(f"Error fetching project configuration: {error}")
            raise Exception(f"Failed to fetch project configuration: {error}. Cannot proceed with deployment.")

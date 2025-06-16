import boto3
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from infrastructure.types import ECSInfrastructureArgs, ECSInfrastructureOutput, EnvironmentVariable
from infrastructure import ECSInfrastructure
from core.database import prisma
from services.encryption_service import encryption_service

logger = logging.getLogger(__name__)


class DeploymentConfig:
    def __init__(
        self,
        project_id: str,
        project_name: str,
        git_repo_url: str,
        branch: str,
        commit_sha: str,
        subdirectory: Optional[str] = None,
        health_check_path: str = "/",
        port: int = 3000,
        cpu: int = 256,
        memory: int = 512,
        disk_size: int = 21
    ):
        self.project_id = project_id
        self.project_name = project_name
        self.git_repo_url = git_repo_url
        self.branch = branch
        self.commit_sha = commit_sha
        self.subdirectory = subdirectory
        self.health_check_path = health_check_path
        self.port = port
        self.cpu = cpu
        self.memory = memory
        self.disk_size = disk_size


class DeploymentService:
    def __init__(self, region: str = None, aws_credentials: Optional[dict] = None):
        if region is None:
            region = os.getenv('AWS_REGION', 'us-east-1')
        self.region = region
        self.deployment_logs: Dict[str, List[str]] = {}
        self.aws_credentials = aws_credentials
        
        # Initialize AWS clients with custom credentials if provided
        client_config = {"region_name": region}
        if aws_credentials:
            client_config.update({
                "aws_access_key_id": aws_credentials["access_key"],
                "aws_secret_access_key": aws_credentials["secret_key"]
            })
        
        self.sts = boto3.client("sts", **client_config)
        self.ecr = boto3.client("ecr", **client_config)
        self.s3 = boto3.client("s3", **client_config)
        self.codebuild = boto3.client("codebuild", **client_config)
        self.cloudwatch_logs = boto3.client("logs", **client_config)
        self.secretsmanager = boto3.client("secretsmanager", **client_config)
    
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
            if prisma.is_connected():
                logs_text = "\n".join(self.deployment_logs[deployment_id])
                await prisma.deployment.update(
                    where={"id": deployment_id},
                    data={"logs": logs_text}
                )
            
            logger.info(f"[{deployment_id}] {message}")
        except Exception as error:
            logger.error(f"Failed to log to database: {error}")
    
    async def execute_with_logging(
        self, 
        command: str, 
        project_id: str, 
        deployment_id: Optional[str] = None,
        cwd: Optional[str] = None
    ) -> str:
        """Execute command with logging"""
        if deployment_id:
            await self.log_to_database(deployment_id, f"Executing: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = f"Command failed: {result.stderr}"
                if deployment_id:
                    await self.log_to_database(deployment_id, f"Error: {error_msg}")
                raise Exception(error_msg)
            
            if deployment_id and result.stdout.strip():
                await self.log_to_database(deployment_id, f"Output: {result.stdout.strip()}")
            
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
    
    async def get_ecr_registry(self) -> str:
        """Get ECR registry URL"""
        try:
            response = self.sts.get_caller_identity()
            account_id = response["Account"]
            return f"{account_id}.dkr.ecr.{self.region}.amazonaws.com"
        except Exception as error:
            raise Exception(f"Failed to get AWS account ID: {error}")
    
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
                encryptionConfiguration={"encryptionType": "AES256"}
            )
            
            logger.info(f"Created ECR repository: {repository_name}")
    
    async def deploy_project(
        self, 
        config: DeploymentConfig, 
        deployment_id: Optional[str] = None
    ) -> ECSInfrastructureOutput:
        """Deploy project to AWS infrastructure"""
        clone_dir: Optional[str] = None
        
        try:
            # Register deployment for tracking
            if deployment_id:
                await self.log_to_database(deployment_id, "🚀 Starting deployment process...")
            
            # Step 1: Clone repository
            if deployment_id:
                await self.log_to_database(deployment_id, "📥 Cloning repository...")
            clone_dir = await self.clone_repository(
                config.git_repo_url, 
                config.branch, 
                config.commit_sha, 
                config.project_id, 
                deployment_id
            )
            
            # Step 2: Build and push Docker image
            if deployment_id:
                await self.log_to_database(deployment_id, "🐳 Building and pushing Docker image...")
            image_uri = await self.build_and_push_image(
                config.project_name,
                config.commit_sha,
                clone_dir,
                config.project_id,
                deployment_id,
                config.subdirectory
            )
            
            # Step 3: Deploy infrastructure using AWS API
            if deployment_id:
                await self.log_to_database(deployment_id, "☁️ Provisioning AWS infrastructure...")
            result = await self.deploy_infrastructure(
                config,
                image_uri,
                deployment_id
            )
            
            # Wait for service to become healthy before marking as completed
            if deployment_id:
                await self.log_to_database(deployment_id, "🔄 Waiting for service to become healthy...")
                
                # Wait for service to be ready
                success = await self.wait_for_service_healthy(
                    config.project_id, 
                    deployment_id,
                    max_wait_minutes=15
                )
                
                if success:
                    await self.log_to_database(deployment_id, "✅ Deployment completed successfully!")
                    
                    # Update deployment status in database
                    await prisma.deployment.update(
                        where={"id": deployment_id},
                        data={
                            "status": "SUCCESS"
                        }
                    )
                    
                    # Update project status to deployed
                    await prisma.project.update(
                        where={"id": config.project_id},
                        data={
                            "status": "DEPLOYED"
                        }
                    )
                else:
                    await self.log_to_database(deployment_id, "❌ Service failed to become healthy within timeout")
                    
                    # Update deployment status to failed
                    await prisma.deployment.update(
                        where={"id": deployment_id},
                        data={
                            "status": "FAILED"
                        }
                    )
                    
                    # Update project status to failed
                    await prisma.project.update(
                        where={"id": config.project_id},
                        data={"status": "FAILED"}
                    )
            
            return result
            
        except Exception as error:
            error_message = str(error)
            logger.error(f"Deployment failed: {error}")
            
            if deployment_id:
                await self.log_to_database(deployment_id, f"❌ Deployment failed: {error_message}")
                
                # Update deployment status to failed
                await prisma.deployment.update(
                    where={"id": deployment_id},
                    data={
                        "status": "FAILED"
                    }
                )
                
                # Update project status to failed
                await prisma.project.update(
                    where={"id": config.project_id},
                    data={"status": "FAILED"}
                )
            
            raise error
        finally:
            # Clean up clone directory
            if clone_dir and os.path.exists(clone_dir):
                try:
                    shutil.rmtree(clone_dir)
                    if deployment_id:
                        await self.log_to_database(deployment_id, "🧹 Cleaned up temporary files")
                    logger.info(f"Cleaned up clone directory: {clone_dir}")
                except Exception as error:
                    logger.warning(f"Failed to clean up clone directory: {error}")
    
    async def clone_repository(
        self,
        git_repo_url: str,
        branch: str,
        commit_sha: str,
        project_id: str,
        deployment_id: Optional[str] = None
    ) -> str:
        """Clone git repository"""
        clone_dir = tempfile.mkdtemp(prefix="clone-")
        
        try:
            if deployment_id:
                await self.log_to_database(deployment_id, f"Cloning repository: {git_repo_url}")
            
            # Get GitHub access token for the user
            github_token = await self.get_github_token(project_id)
            
            # Create authenticated clone URL
            authenticated_url = await self.create_authenticated_git_url(git_repo_url, github_token)
            
            if deployment_id:
                await self.log_to_database(deployment_id, "Using GitHub authentication for private repository access")
            
            await self.execute_with_logging(
                f"git clone -b {branch} {authenticated_url} {clone_dir}",
                project_id,
                deployment_id
            )
            
            if deployment_id:
                await self.log_to_database(deployment_id, f"Checked out branch: {branch} (commit: {commit_sha})")
            
            # Check for Dockerfile
            if deployment_id:
                await self.log_to_database(deployment_id, "Checking for Dockerfile...")
            
            dockerfile_path = os.path.join(clone_dir, "Dockerfile")
            if not os.path.exists(dockerfile_path):
                error_message = "Dockerfile not found in repository. Please add a Dockerfile to your project."
                raise Exception(error_message)
            
            if deployment_id:
                await self.log_to_database(deployment_id, "✅ Found Dockerfile in repository")
            
            return clone_dir
            
        except Exception as error:
            # Clean up on error
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)
            raise Exception(f"Failed to clone repository: {error}")
    
    async def get_github_token(self, project_id: str) -> str:
        """Get GitHub access token for project user"""
        try:
            # Get the project to find the user
            project = await prisma.project.find_unique(
                where={"id": project_id},
                include={
                    "user": {
                        "include": {
                            "accounts": {
                                "where": {"provider": "github"}
                            }
                        }
                    }
                }
            )

            if not project or not project.user or not project.user.accounts or len(project.user.accounts) == 0:
                # Fallback to environment variable
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    raise Exception("GitHub access token not found. Please reconnect your GitHub account.")
                return token

            return project.user.accounts[0].access_token
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
        subdirectory: Optional[str] = None
    ) -> str:
        """Build and push Docker image to ECR"""
        ecr_registry = await self.get_ecr_registry()
        repository_name = project_name.lower().replace("[^a-z0-9-_]", "-")
        image_tag = f"{repository_name}:{commit_sha}"
        image_uri = f"{ecr_registry}/{image_tag}"
        
        try:
            # Ensure ECR repository exists
            if deployment_id:
                await self.log_to_database(deployment_id, f"Ensuring ECR repository exists: {repository_name}")
            await self.ensure_ecr_repository(repository_name)
            
            # Start CodeBuild project to build and push image
            if deployment_id:
                await self.log_to_database(deployment_id, "Starting CodeBuild project for container build...")
                if subdirectory:
                    await self.log_to_database(deployment_id, f"📁 Build context: subdirectory '{subdirectory}'")
            
            build_id = await self.start_codebuild(
                project_name,
                repository_name,
                commit_sha,
                clone_dir,
                project_id,
                deployment_id,
                subdirectory
            )
            
            if deployment_id:
                await self.log_to_database(deployment_id, f"CodeBuild started: {build_id}")
            
            # Wait for build to complete
            await self.wait_for_codebuild_completion(build_id, deployment_id)
            
            if deployment_id:
                await self.log_to_database(deployment_id, f"✅ Successfully built and pushed image: {image_uri}")
            
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
        subdirectory: Optional[str] = None
    ) -> str:
        """Start CodeBuild project"""
        # Upload source to S3 first
        source_location = await self.upload_source_to_s3(clone_dir, project_name, commit_sha)
        
        import re
        build_project_name = f"{re.sub(r'[^a-z0-9-]', '-', project_name.lower())}-build"
        
        # Get environment variables for the project to use as build args
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
        
        # Create buildspec content
        ecr_registry = await self.get_ecr_registry()
        
        # Build the buildspec as a proper YAML structure
        buildspec_content = f"""version: 0.2
phases:
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {ecr_registry}"""
        
        if subdirectory:
            buildspec_content += f"""
      - echo Changing to subdirectory {subdirectory}
      - cd {subdirectory}"""
        
        buildspec_content += f"""
  build:
    commands:
      - echo Build started on `date`
      - echo Building the Docker image...
      - docker build{build_args} -t {repository_name}:{commit_sha} .
      - docker tag {repository_name}:{commit_sha} {ecr_registry}/{repository_name}:{commit_sha}
  post_build:
    commands:
      - echo Build completed on `date`
      - echo Pushing the Docker image...
      - docker push {ecr_registry}/{repository_name}:{commit_sha}"""
        
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
                await self.log_to_database(deployment_id, f"Created CloudWatch log group: {log_group_name}")
        except self.cloudwatch_logs.exceptions.ResourceAlreadyExistsException:
            pass  # Log group already exists
        except Exception as error:
            logger.warning(f"Failed to create log group: {error}")
        
        params = {
            "name": build_project_name,
            "source": {
                "type": "S3",
                "location": source_location,
                "buildspec": buildspec
            },
            "artifacts": {"type": "NO_ARTIFACTS"},
            "environment": {
                "type": "LINUX_CONTAINER",
                "image": "aws/codebuild/amazonlinux2-x86_64-standard:4.0",
                "computeType": "BUILD_GENERAL1_SMALL",
                "privilegedMode": True
            },
            "logsConfig": {
                "cloudWatchLogs": {
                    "status": "ENABLED",
                    "groupName": log_group_name
                }
            },
            "serviceRole": await self.get_codebuild_role()
        }
        
        # Create or update CodeBuild project
        try:
            self.codebuild.create_project(**params)
            if deployment_id:
                await self.log_to_database(deployment_id, f"Created CodeBuild project: {build_project_name}")
        except self.codebuild.exceptions.ResourceAlreadyExistsException:
            # Update existing project
            self.codebuild.update_project(**params)
            if deployment_id:
                await self.log_to_database(deployment_id, f"Updated CodeBuild project: {build_project_name}")
        
        # Start build
        result = self.codebuild.start_build(projectName=build_project_name)
        
        return result["build"]["id"]
    
    async def wait_for_codebuild_completion(self, build_id: str, deployment_id: Optional[str] = None):
        """Wait for CodeBuild to complete"""
        log_group_name: Optional[str] = None
        log_stream_name: Optional[str] = None
        next_token: Optional[str] = None
        log_stream_found = False
        
        while True:
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
                        log_group_part = arn_parts[6]  # log-group:/aws/codebuild/project
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
                        "startFromHead": True
                    }
                    
                    # Only add nextToken if it exists and is not None
                    if next_token:
                        params["nextToken"] = next_token
                                        
                    logs_result = self.cloudwatch_logs.get_log_events(**params)
                    
                    events = logs_result.get("events", [])
                    
                    for event in events:
                        if event.get("message") and event["message"].strip():
                            await self.log_to_database(deployment_id, f"🔨 {event['message'].strip()}")
                    
                    # Update nextToken for next iteration
                    new_next_token = logs_result.get("nextForwardToken")
                    if new_next_token != next_token:  # Only update if it's different
                        next_token = new_next_token
                        
                except Exception as error:
                    if deployment_id:
                        await self.log_to_database(deployment_id, f"❌ Log streaming error: {str(error)}")
                    logger.warning(f"Failed to stream logs: {error}")
            
            if deployment_id:
                # Only log status changes
                if not hasattr(self, '_last_build_status') or self._last_build_status != status:
                    await self.log_to_database(deployment_id, f"CodeBuild status: {status}")
                    self._last_build_status = status
            
            if status == "SUCCEEDED":
                # Get final logs
                if log_group_name and log_stream_name and deployment_id:
                    try:
                        final_logs = self.cloudwatch_logs.get_log_events(
                            logGroupName=log_group_name,
                            logStreamName=log_stream_name,
                            nextToken=next_token,
                            startFromHead=True
                        )
                        
                        for event in final_logs.get("events", []):
                            if event.get("message"):
                                await self.log_to_database(deployment_id, f"🔨 {event['message'].strip()}")
                    except Exception as error:
                        logger.warning(f"Failed to get final logs: {error}")
                return
            elif status in ["FAILED", "FAULT", "STOPPED", "TIMED_OUT"]:
                if log_group_name and deployment_id:
                    await self.log_to_database(
                        deployment_id, 
                        f"❌ CodeBuild logs available in CloudWatch: {log_group_name}"
                    )
                raise Exception(f"CodeBuild failed with status: {status}")
            
            # Wait 5 seconds before checking again
            time.sleep(5)
    
    async def upload_source_to_s3(self, clone_dir: str, project_name: str, commit_sha: str) -> str:
        """Upload source code to S3"""
        bucket_name = f"{project_name.lower().replace('[^a-z0-9-]', '-')}-builds-{self.region}"
        key_name = f"source/{commit_sha}.zip"
        
        # Create bucket if it doesn't exist
        try:
            if self.region == "us-east-1":
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": self.region}
                )
        except self.s3.exceptions.BucketAlreadyOwnedByYou:
            pass  # Bucket already exists
        except self.s3.exceptions.BucketAlreadyExists:
            pass  # Bucket already exists
        
        # Create zip of source code using Python
        import zipfile
        import os
        
        zip_path = f"/tmp/{commit_sha}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(clone_dir):
                # Skip .git directories
                dirs[:] = [d for d in dirs if not d.startswith('.git')]
                
                for file in files:
                    # Skip .git files
                    if '.git' in file:
                        continue
                        
                    file_path = os.path.join(root, file)
                    arc_name = os.path.relpath(file_path, clone_dir)
                    zipf.write(file_path, arc_name)
        
        # Upload to S3
        with open(zip_path, "rb") as f:
            self.s3.upload_fileobj(f, bucket_name, key_name)
        
        # Clean up local zip
        os.remove(zip_path)
        
        return f"{bucket_name}/{key_name}"
    
    async def get_codebuild_role(self) -> str:
        """Get CodeBuild service role ARN"""
        response = self.sts.get_caller_identity()
        account_id = response["Account"]
        return f"arn:aws:iam::{account_id}:role/CodeBuildServiceRole"
    
    async def deploy_infrastructure(
        self,
        config: DeploymentConfig,
        image_uri: str,
        deployment_id: Optional[str] = None
    ) -> ECSInfrastructureOutput:
        """Deploy AWS infrastructure"""
        # Fetch environment variables for the project
        environment_variables = await self.get_environment_variables(config.project_id)
        
        if deployment_id and environment_variables:
            await self.log_to_database(deployment_id, f"📋 Found {len(environment_variables)} environment variables")
        
        # Fetch project to get network configuration (for existing VPC/subnets/cluster only)
        project_network = await self.get_project_network_config(config.project_id)
        
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
            existing_vpc_id=project_network.get("existing_vpc_id"),
            existing_subnet_ids=project_network.get("existing_subnet_ids"),
            existing_cluster_arn=project_network.get("existing_cluster_arn")
        )
        
        # Add existing network resources if configured
        if project_network.get("existing_vpc_id"):
            if deployment_id:
                await self.log_to_database(deployment_id, f"🌐 Using existing VPC: {project_network['existing_vpc_id']}")
        
        if project_network.get("existing_subnet_ids"):
            if deployment_id:
                subnet_list = ", ".join(project_network["existing_subnet_ids"])
                await self.log_to_database(deployment_id, f"🌐 Using existing subnets: {subnet_list}")
        
        if project_network.get("existing_cluster_arn"):
            if deployment_id:
                await self.log_to_database(deployment_id, f"🚀 Using existing ECS cluster: {project_network['existing_cluster_arn']}")
        
        infrastructure = ECSInfrastructure(infrastructure_args, aws_credentials=self.aws_credentials)
        
        if deployment_id:
            await self.log_to_database(deployment_id, "Creating/updating AWS infrastructure...")
            await self.log_to_database(
                deployment_id, 
                f"- Resource allocation: {config.cpu} CPU units, "
                f"{config.memory} MB memory, {config.disk_size} GB disk"
            )
            await self.log_to_database(deployment_id, "- Setting up VPC and networking")
            await self.log_to_database(deployment_id, "- Creating security groups")
            await self.log_to_database(deployment_id, "- Setting up ECS cluster and service")
            await self.log_to_database(deployment_id, "- Configuring load balancer")
            if environment_variables:
                await self.log_to_database(
                    deployment_id, 
                    f"- Configuring {len(environment_variables)} environment variables and secrets"
                )
        
        result = await infrastructure.create_or_update_infrastructure()
        
        if deployment_id:
            await self.log_to_database(deployment_id, "✅ Infrastructure ready!")
            await self.log_to_database(deployment_id, f"- ECS Service: {result.service_arn}")
            await self.log_to_database(deployment_id, f"- Load Balancer: {result.load_balancer_dns}")
        
        # Update project with deployed resource ARNs (only fields that exist in schema)
        update_data = {}
        if result.service_arn:
            update_data["ecsServiceArn"] = result.service_arn
        if result.cluster_arn:
            update_data["ecsClusterArn"] = result.cluster_arn
        if result.load_balancer_arn:  # Use load_balancer_arn instead of alb_arn
            update_data["albArn"] = result.load_balancer_arn
        if result.load_balancer_dns:  # Set the domain field for the project
            update_data["domain"] = result.load_balancer_dns
        
        if update_data:
            await prisma.project.update(
                where={"id": config.project_id},
                data=update_data
            )
        
        return result
    
    async def wait_for_service_healthy(self, project_id: str, deployment_id: str, max_wait_minutes: int = 15) -> bool:
        """Wait for ECS service to become healthy"""
        import boto3
        import asyncio
        from botocore.exceptions import ClientError
        
        try:
            # Get project details
            project = await prisma.project.find_unique(where={"id": project_id})
            if not project or not project.ecsServiceArn or not project.ecsClusterArn:
                await self.log_to_database(deployment_id, "❌ Missing ECS service or cluster information")
                return False
            
            region = os.getenv('AWS_REGION', 'us-east-1')
            
            # Use the same credentials as the deployment service
            client_config = {"region_name": region}
            if self.aws_credentials:
                client_config.update({
                    "aws_access_key_id": self.aws_credentials["access_key"],
                    "aws_secret_access_key": self.aws_credentials["secret_key"]
                })
            
            ecs_client = boto3.client('ecs', **client_config)
            
            cluster_arn = project.ecsClusterArn
            service_arn = project.ecsServiceArn
            
            start_time = asyncio.get_event_loop().time()
            max_wait_seconds = max_wait_minutes * 60
            check_interval = 30  # Check every 30 seconds
            
            await self.log_to_database(deployment_id, f"Monitoring service health for up to {max_wait_minutes} minutes...")
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                
                if elapsed > max_wait_seconds:
                    await self.log_to_database(deployment_id, f"⏰ Timeout after {max_wait_minutes} minutes")
                    return False
                
                try:
                    # Check service status
                    response = ecs_client.describe_services(
                        cluster=cluster_arn,
                        services=[service_arn]
                    )
                    
                    if not response['services']:
                        await self.log_to_database(deployment_id, "❌ Service not found")
                        return False
                    
                    service = response['services'][0]
                    
                    # Get service metrics
                    service_status = service['status']
                    running_count = service.get('runningCount', 0)
                    desired_count = service.get('desiredCount', 0)
                    pending_count = service.get('pendingCount', 0)
                    
                    # Check deployment status
                    deployments = service.get('deployments', [])
                    primary_deployment = None
                    for deployment in deployments:
                        if deployment['status'] == 'PRIMARY':
                            primary_deployment = deployment
                            break
                    
                    deployment_stable = False
                    if primary_deployment:
                        rollout_state = primary_deployment.get('rolloutState', '')
                        deployment_running = primary_deployment.get('runningCount', 0)
                        deployment_desired = primary_deployment.get('desiredCount', 0)
                        deployment_stable = (
                            rollout_state == 'COMPLETED' and 
                            deployment_running == deployment_desired
                        )
                    
                    # Check if service is healthy
                    service_healthy = (
                        service_status == 'ACTIVE' and
                        running_count == desired_count and
                        running_count > 0 and
                        pending_count == 0 and
                        deployment_stable
                    )
                    
                    if service_healthy:
                        await self.log_to_database(
                            deployment_id, 
                            f"✅ Service is healthy! {running_count}/{desired_count} tasks running"
                        )
                        return True
                    else:
                        # Log current status
                        status_msg = f"Service status: {running_count}/{desired_count} running"
                        if pending_count > 0:
                            status_msg += f", {pending_count} pending"
                        if primary_deployment:
                            status_msg += f", rollout: {primary_deployment.get('rolloutState', 'unknown')}"
                        
                        await self.log_to_database(deployment_id, f"🔄 {status_msg}")
                        
                        # Check for failures in recent events
                        events = service.get('events', [])[:5]
                        for event in events:
                            message = event.get('message', '').lower()
                            if any(keyword in message for keyword in ['failed', 'stopped', 'unhealthy']):
                                await self.log_to_database(
                                    deployment_id, 
                                    f"⚠️ Service event: {event.get('message', '')}"
                                )
                
                except ClientError as e:
                    await self.log_to_database(deployment_id, f"❌ Error checking service: {e}")
                    return False
                
                # Wait before next check
                await asyncio.sleep(check_interval)
                
        except Exception as e:
            await self.log_to_database(deployment_id, f"❌ Error monitoring service health: {e}")
            return False
    
    async def get_environment_variables(self, project_id: str) -> List[EnvironmentVariable]:
        """Get environment variables for project"""
        try:
            env_vars = await prisma.environmentvariable.find_many(
                where={"projectId": project_id}
            )

            return [
                EnvironmentVariable(
                    key=env_var.key,
                    value=env_var.value if not env_var.isSecret else None,
                    is_secret=env_var.isSecret,
                    secret_key=env_var.secretKey if env_var.isSecret else None
                )
                for env_var in env_vars
            ]
        except Exception as error:
            logger.error(f"Error fetching environment variables: {error}")
            return []
    
    async def get_project_network_config(self, project_id: str) -> Dict:
        """Get project network configuration"""
        try:
            project = await prisma.project.find_unique(
                where={"id": project_id}
            )

            if not project:
                return {
                    "existing_vpc_id": None,
                    "existing_subnet_ids": None,
                    "existing_cluster_arn": None,
                    "cpu": 256,
                    "memory": 512,
                    "disk_size": 21,
                    "port": 3000,
                    "health_check_path": "/"
                }

            # Parse existing subnet IDs if they exist
            existing_subnet_ids = None
            if project.existingSubnetIds:
                try:
                    existing_subnet_ids = json.loads(project.existingSubnetIds)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse existing subnet IDs: {project.existingSubnetIds}")

            return {
                "existing_vpc_id": project.existingVpcId,
                "existing_subnet_ids": existing_subnet_ids,
                "existing_cluster_arn": project.existingClusterArn,
                "cpu": project.cpu or 256,
                "memory": project.memory or 512,
                "disk_size": project.diskSize or 21,
                "port": project.port or 3000,
                "health_check_path": project.healthCheckPath or "/"
            }
        except Exception as error:
            logger.error(f"Error fetching project configuration: {error}")
            return {
                "existing_vpc_id": None,
                "existing_subnet_ids": None,
                "existing_cluster_arn": None,
                "cpu": 256,
                "memory": 512,
                "disk_size": 21,
                "port": 3000,
                "health_check_path": "/"
            }
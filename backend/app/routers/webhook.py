from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
import asyncio
import hashlib
import hmac
import json
import logging
from typing import Dict, Any

from core.database import prisma
from services.deployment import DeploymentService, DeploymentConfig
from services.encryption_service import encryption_service
from schemas import DeploymentStatus, EnvironmentStatus
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature.startswith("sha256="):
        return False

    expected_signature = (
        "sha256="
        + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    )

    return hmac.compare_digest(signature, expected_signature)


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook for automatic deployments"""
    try:
        # Get headers
        signature = request.headers.get("X-Hub-Signature-256")
        event_type = request.headers.get("X-GitHub-Event")

        if not signature or not event_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required headers",
            )

        # Get raw payload
        payload = await request.body()

        # Parse JSON payload
        try:
            payload_data = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
            )

        # Only handle push events
        if event_type != "push":
            logger.info(f"Ignoring webhook event type: {event_type}")
            return {"message": "Event type not supported"}

        # Extract repository info
        repository = payload_data.get("repository", {})
        repo_url = repository.get("clone_url", "").replace(".git", "")

        # Convert to HTTPS GitHub URL format
        if repo_url.startswith("https://github.com/"):
            github_url = repo_url
        else:
            logger.warning(f"Unexpected repository URL format: {repo_url}")
            return {"message": "Repository URL format not supported"}

        # Extract branch from ref
        ref = payload_data.get("ref", "")
        if not ref.startswith("refs/heads/"):
            logger.info(f"Ignoring non-branch ref: {ref}")
            return {"message": "Not a branch push"}

        branch = ref.replace("refs/heads/", "")

        logger.info(f"Webhook: Push to {github_url} branch {branch}")

        # Find webhook by repository URL
        webhook = await prisma.webhook.find_unique(
            where={"gitRepoUrl": github_url}, include={"projects": True}
        )

        if not webhook:
            logger.info(f"No webhook configured for repository {github_url}")
            return {"message": "No webhook configured for this repository"}

        if not webhook.isActive:
            logger.info(f"Webhook for repository {github_url} is not active")
            return {"message": "Webhook is not active"}

        # Verify webhook signature using shared secret
        if not verify_github_signature(payload, signature, webhook.secret):
            logger.warning(f"Invalid webhook signature for repository {github_url}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        # Find environments that match the push branch
        # Get all projects for this webhook
        projects = webhook.projects
        
        # Find environments across all projects that match the branch
        environments_to_deploy = []
        for project in projects:
            # Get environments for this project that match the branch
            project_environments = await prisma.environment.find_many(
                where={
                    "projectId": project.id,
                    "branch": branch
                },
                include={
                    "project": {"include": {"team": True}},
                    "teamAwsConfig": True
                }
            )
            environments_to_deploy.extend(project_environments)

        if not environments_to_deploy:
            logger.info(
                f"No environments found with branch {branch} for {github_url}"
            )
            return {"message": f"No environments configured for branch {branch}"}

        # Extract changed files from commits
        changed_files = set()
        for commit in payload_data.get("commits", []):
            changed_files.update(commit.get("added", []))
            changed_files.update(commit.get("modified", []))
            changed_files.update(commit.get("removed", []))

        logger.info(f"Changed files in push: {changed_files}")
        logger.info(f"Found {len(environments_to_deploy)} environments for {github_url}:{branch}")

        # Filter environments based on subdirectory changes
        environments_to_deploy_filtered = []

        for environment in environments_to_deploy:
            project = environment.project
            
            # Check if environment is not already deploying
            if environment.status in ["DEPLOYING", "BUILDING", "CLONING"]:
                logger.info(f"Environment {environment.name} in project {project.name} already deploying, skipping")
                continue

            # Check if project subdirectory has changes
            should_deploy = False

            if not project.subdirectory:
                # Projects without subdirectory deploy on any change
                should_deploy = True
                logger.info(
                    f"Environment {environment.name} in project {project.name} has no subdirectory, will deploy on any change"
                )
            else:
                # Check if any changed file is in the project's subdirectory
                subdirectory_prefix = project.subdirectory.rstrip("/") + "/"
                logger.info(
                    f"Environment {environment.name} in project {project.name}: Checking subdirectory '{project.subdirectory}' (prefix: '{subdirectory_prefix}') against files: {list(changed_files)}"
                )
                for file_path in changed_files:
                    if (
                        file_path.startswith(subdirectory_prefix)
                        or file_path == project.subdirectory
                    ):
                        should_deploy = True
                        logger.info(
                            f"Environment {environment.name} in project {project.name} subdirectory '{project.subdirectory}' has changes in file: {file_path}"
                        )
                        break

                if not should_deploy:
                    logger.info(
                        f"Environment {environment.name} in project {project.name} subdirectory '{project.subdirectory}' has no changes, skipping deployment"
                    )

            if should_deploy:
                environments_to_deploy_filtered.append(environment)

        # Trigger all environment deployments concurrently
        deployed_environments = []
        if environments_to_deploy_filtered:
            # Create deployment tasks for all environments in parallel
            deployment_tasks = []
            for environment in environments_to_deploy_filtered:
                logger.info(f"Triggering auto-deployment for environment {environment.name} in project {environment.project.name}")
                task = asyncio.create_task(
                    trigger_environment_deployment(environment, payload_data)
                )
                deployment_tasks.append(task)
                deployed_environments.append({
                    "project": environment.project.name,
                    "environment": environment.name
                })

            # Add a single background task to wait for all deployments
            background_tasks.add_task(wait_for_deployments, deployment_tasks)

        if deployed_environments:
            return {
                "message": f"Triggered deployments for {len(deployed_environments)} environments",
                "environments": deployed_environments,
            }
        else:
            return {"message": "No deployments triggered"}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}",
        )


async def wait_for_deployments(deployment_tasks):
    """Wait for all deployment tasks to complete"""
    try:
        await asyncio.gather(*deployment_tasks, return_exceptions=True)
        logger.info("All webhook-triggered deployments completed")
    except Exception as e:
        logger.error(f"Error waiting for webhook deployments: {e}")


async def trigger_auto_deployment(project_id: str, webhook_payload: Dict[str, Any]):
    """Trigger automatic deployment for a project"""
    try:
        # Get commit info from payload
        commits = webhook_payload.get("commits", [])
        latest_commit = commits[-1] if commits else {}
        commit_sha = latest_commit.get("id", "unknown")
        commit_message = latest_commit.get(
            "message", "Auto-deploy triggered by webhook"
        )

        logger.info(
            f"Starting auto-deployment for project {project_id}, commit {commit_sha}"
        )

        # Get project with team info for credential selection
        project = await prisma.project.find_unique(
            where={"id": project_id}, include={"team": True}
        )
        if not project:
            logger.error(f"Project {project_id} not found")
            return

        # Create deployment record
        deployment = await prisma.deployment.create(
            data={
                "projectId": project_id,
                "status": "PENDING",
                "imageTag": f"{project.name}:{commit_sha}",
                "commitSha": commit_sha,
                "logs": f"🤖 Auto-deployment triggered by webhook\nCommit: {commit_sha}\nMessage: {commit_message}\n\n",
            }
        )

        # Get team AWS credentials (all projects belong to teams)
        team_aws_config = await prisma.teamawsconfig.find_first(
            where={"teamId": project.teamId, "isActive": True}
        )

        if not team_aws_config:
            logger.error(f"Project {project_id} has no team AWS credentials configured")
            return

        # Decrypt team credentials
        from services.encryption_service import EncryptionService

        encryption_service = EncryptionService()
        access_key = encryption_service.decrypt(team_aws_config.awsAccessKeyId)
        secret_key = encryption_service.decrypt(team_aws_config.awsSecretAccessKey)

        if not access_key or not secret_key:
            logger.error(f"Project {project_id} has invalid team AWS credentials")
            return

        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
        aws_region = team_aws_config.awsRegion
        logger.info(f"Using team AWS credentials for project {project_id}")

        # Initialize deployment service with proper credentials
        deployment_service = DeploymentService(
            region=aws_region, aws_credentials=aws_credentials
        )

        # Create deployment configuration
        config = DeploymentConfig(
            project_id=project_id,
            project_name=project.name,
            git_repo_url=project.gitRepoUrl,
            branch=project.branch or "main",
            commit_sha=commit_sha,
            subdirectory=project.subdirectory,
            health_check_path=project.healthCheckPath or "/",
            port=project.port or 3000,
            cpu=project.cpu or 256,
            memory=project.memory or 512,
            disk_size=project.diskSize or 21,
        )

        # Start deployment
        await deployment_service.deploy_project(
            config=config, deployment_id=deployment.id
        )

        logger.info(f"Auto-deployment completed for project {project_id}")

    except Exception as e:
        logger.error(f"Auto-deployment failed for project {project_id}: {e}")

        # Update deployment status to failed if deployment record exists
        try:
            await prisma.deployment.update_many(
                where={
                    "projectId": project_id,
                    "status": {"in": ["PENDING", "BUILDING", "DEPLOYING"]},
                },
                data={"status": "FAILED"},
            )
        except:
            pass


async def trigger_environment_deployment(environment, webhook_payload: Dict[str, Any]):
    """Trigger automatic deployment for an environment"""
    try:
        # Get commit info from payload
        commits = webhook_payload.get("commits", [])
        latest_commit = commits[-1] if commits else {}
        commit_sha = latest_commit.get("id", "unknown")
        commit_message = latest_commit.get(
            "message", "Auto-deploy triggered by webhook"
        )

        logger.info(
            f"Starting environment auto-deployment for {environment.project.name}/{environment.name}, commit {commit_sha}"
        )

        # Create deployment record
        deployment = await prisma.deployment.create(
            data={
                "projectId": environment.project.id,
                "environmentId": environment.id,
                "status": DeploymentStatus.PENDING,
                "imageTag": f"{environment.project.name}-{environment.name}:{commit_sha}",
                "commitSha": commit_sha,
                "logs": f"🤖 Auto-deployment triggered by webhook\nCommit: {commit_sha}\nMessage: {commit_message}\n\n",
            }
        )

        # Update environment status
        await prisma.environment.update(
            where={"id": environment.id}, 
            data={"status": EnvironmentStatus.DEPLOYING}
        )

        # Get team AWS credentials
        team_aws_config = environment.teamAwsConfig
        if not team_aws_config:
            logger.error(f"Environment {environment.id} has no AWS credentials configured")
            return

        # Decrypt team credentials
        access_key = encryption_service.decrypt(team_aws_config.awsAccessKey)
        secret_key = encryption_service.decrypt(team_aws_config.awsSecretKey)
        aws_credentials = {"access_key": access_key, "secret_key": secret_key}
        aws_region = team_aws_config.awsRegion

        # Start deployment
        deployment_service = DeploymentService(
            region=aws_region, aws_credentials=aws_credentials
        )

        # Create deployment configuration
        config = DeploymentConfig(
            project_id=environment.project.id,
            project_name=f"{environment.project.name[:23] if len(f'{environment.project.name}-{environment.name}') > 32 else environment.project.name}-{environment.name[:8] if len(f'{environment.project.name}-{environment.name}') > 32 else environment.name}",
            git_repo_url=environment.project.gitRepoUrl,
            branch=environment.branch or "main",
            commit_sha=commit_sha,
            environment_id=environment.id,
            subdirectory=environment.project.subdirectory,
            health_check_path=environment.project.healthCheckPath or "/",
            port=environment.project.port or 3000,
            cpu=environment.cpu or 256,
            memory=environment.memory or 512,
            disk_size=environment.diskSize or 21,
        )

        await deployment_service.deploy_project(
            config=config, deployment_id=deployment.id
        )

        logger.info(f"Environment auto-deployment completed for {environment.project.name}/{environment.name}")

    except Exception as e:
        logger.error(f"Environment auto-deployment failed for {environment.project.name}/{environment.name}: {e}")

        # Update deployment status to failed if deployment record exists
        try:
            await prisma.deployment.update_many(
                where={
                    "environmentId": environment.id,
                    "status": {"in": ["PENDING", "BUILDING", "DEPLOYING"]},
                },
                data={"status": DeploymentStatus.FAILED},
            )
            # Reset environment status
            await prisma.environment.update(
                where={"id": environment.id}, 
                data={"status": EnvironmentStatus.CREATED}
            )
        except:
            pass

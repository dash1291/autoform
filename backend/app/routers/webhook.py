from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
import hashlib
import hmac
import json
import logging
from typing import Dict, Any

from core.database import prisma
from services.deployment import DeploymentService, DeploymentConfig

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature.startswith('sha256='):
        return False
    
    expected_signature = 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


@router.post("/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook for automatic deployments"""
    try:
        # Get headers
        signature = request.headers.get('X-Hub-Signature-256')
        event_type = request.headers.get('X-GitHub-Event')
        
        if not signature or not event_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required headers"
            )
        
        # Get raw payload
        payload = await request.body()
        
        # Parse JSON payload
        try:
            payload_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        # Only handle push events
        if event_type != 'push':
            logger.info(f"Ignoring webhook event type: {event_type}")
            return {"message": "Event type not supported"}
        
        # Extract repository info
        repository = payload_data.get('repository', {})
        repo_url = repository.get('clone_url', '').replace('.git', '')
        
        # Convert to HTTPS GitHub URL format
        if repo_url.startswith('https://github.com/'):
            github_url = repo_url
        else:
            logger.warning(f"Unexpected repository URL format: {repo_url}")
            return {"message": "Repository URL format not supported"}
        
        # Extract branch from ref
        ref = payload_data.get('ref', '')
        if not ref.startswith('refs/heads/'):
            logger.info(f"Ignoring non-branch ref: {ref}")
            return {"message": "Not a branch push"}
        
        branch = ref.replace('refs/heads/', '')
        
        logger.info(f"Webhook: Push to {github_url} branch {branch}")
        
        # Find matching projects
        projects = await prisma.project.find_many(
            where={
                "gitRepoUrl": github_url,
                "branch": branch,
                "autoDeployEnabled": True
            }
        )
        
        if not projects:
            logger.info(f"No projects found with auto-deploy enabled for {github_url}:{branch}")
            return {"message": "No matching projects with auto-deploy enabled"}
        
        # Verify webhook signature for each project and trigger deployments
        deployed_projects = []
        
        for project in projects:
            if not project.webhookSecret:
                logger.warning(f"Project {project.name} has auto-deploy enabled but no webhook secret")
                continue
            
            # Verify signature
            if not verify_github_signature(payload, signature, project.webhookSecret):
                logger.warning(f"Invalid webhook signature for project {project.name}")
                continue
            
            # Check if project is not already deploying
            if project.status in ['DEPLOYING', 'BUILDING', 'CLONING']:
                logger.info(f"Project {project.name} already deploying, skipping")
                continue
            
            # Trigger deployment in background
            logger.info(f"Triggering auto-deployment for project {project.name}")
            background_tasks.add_task(trigger_auto_deployment, project.id, payload_data)
            deployed_projects.append(project.name)
        
        if deployed_projects:
            return {
                "message": f"Triggered deployments for {len(deployed_projects)} projects",
                "projects": deployed_projects
            }
        else:
            return {"message": "No deployments triggered"}
        
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed"
        )


async def trigger_auto_deployment(project_id: str, webhook_payload: Dict[str, Any]):
    """Trigger automatic deployment for a project"""
    try:
        # Get commit info from payload
        commits = webhook_payload.get('commits', [])
        latest_commit = commits[-1] if commits else {}
        commit_sha = latest_commit.get('id', 'unknown')
        commit_message = latest_commit.get('message', 'Auto-deploy triggered by webhook')
        
        logger.info(f"Starting auto-deployment for project {project_id}, commit {commit_sha}")
        
        # Get project name for image tag
        project = await prisma.project.find_unique(where={"id": project_id})
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
                "logs": f"🤖 Auto-deployment triggered by webhook\nCommit: {commit_sha}\nMessage: {commit_message}\n\n"
            }
        )
        
        # Initialize deployment service
        deployment_service = DeploymentService()
        
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
            disk_size=project.diskSize or 21
        )
        
        # Start deployment
        await deployment_service.deploy_project(
            config=config,
            deployment_id=deployment.id
        )
        
        logger.info(f"Auto-deployment completed for project {project_id}")
        
    except Exception as e:
        logger.error(f"Auto-deployment failed for project {project_id}: {e}")
        
        # Update deployment status to failed if deployment record exists
        try:
            await prisma.deployment.update_many(
                where={
                    "projectId": project_id,
                    "status": {"in": ["PENDING", "BUILDING", "DEPLOYING"]}
                },
                data={"status": "FAILED"}
            )
        except:
            pass
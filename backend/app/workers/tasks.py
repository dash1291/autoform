"""Celery tasks for deployment operations."""

import os
import sys
import asyncio
import signal
from typing import Dict, Any
from celery import Task
from celery.signals import task_prerun, task_postrun, task_failure
from celery.exceptions import SoftTimeLimitExceeded

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Fix for subprocess issues in Celery workers
if not hasattr(sys.stdout, 'fileno'):
    sys.stdout = sys.__stdout__
if not hasattr(sys.stderr, 'fileno'):
    sys.stderr = sys.__stderr__

from app.workers.celery_app import app
from core.database import prisma
from prisma import Prisma
from schemas import ProjectStatus, DeploymentStatus


class DeploymentTask(Task):
    """Base task class with database session management."""
    
    def __init__(self):
        self.deployment_service = None
    
    def __call__(self, *args, **kwargs):
        """Ensure deployment service is initialized."""
        return self.run(*args, **kwargs)


@app.task(base=DeploymentTask, bind=True, name="deploy_project", max_retries=0, queue="deployments")
def deploy_project(self, config: Dict[str, Any], deployment_id: str):
    """
    Deploy a project using the provided configuration.
    
    Args:
        config: Deployment configuration
        deployment_id: Unique deployment identifier
    """
    # Fix subprocess issues at task runtime
    if not hasattr(sys.stdout, 'fileno'):
        sys.stdout = sys.__stdout__
    if not hasattr(sys.stderr, 'fileno'):
        sys.stderr = sys.__stderr__
    
    # Use asyncio.run for the entire task to avoid event loop issues
    return asyncio.run(_deploy_project_async(self, config, deployment_id))


async def _deploy_project_async(self, config: Dict[str, Any], deployment_id: str):
    """Async implementation of deployment logic."""
    # Create a new Prisma client for this task to avoid event loop issues
    prisma_client = Prisma()
    
    try:
        print(f"Starting deployment task for {deployment_id} (timeout: 18 minutes)")
        
        # Connect to database
        await prisma_client.connect()
        print("Connected to database")
        
        # Update deployment status to in_progress
        deployment = await prisma_client.deployment.find_unique(where={"id": deployment_id})
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")
        
        await prisma_client.deployment.update(
            where={"id": deployment_id},
            data={
                "status": DeploymentStatus.DEPLOYING,
                "celeryTaskId": self.request.id,
                "logs": "🚀 Deployment task started by Celery worker...\n"
            }
        )
        print(f"Updated deployment {deployment_id} status to DEPLOYING")
        
        # Create DeploymentConfig from dict
        from services.deployment import DeploymentConfig, DeploymentService
        from core.database import prisma as global_prisma
        deployment_config = DeploymentConfig(**config)
        print(f"Created deployment config for project {deployment_config.project_id}")
        
        # Ensure global prisma instance is connected (used by DeploymentService)
        if not global_prisma.is_connected():
            await global_prisma.connect()
            print("Connected global Prisma instance for deployment service")
        
        # Initialize deployment service with AWS credentials
        deployment_service = DeploymentService(
            region=deployment_config.aws_region,
            aws_credentials=deployment_config.aws_credentials
        )
        print(f"Initialized deployment service for region {deployment_config.aws_region}")
        
        # Execute deployment with timeout handling
        try:
            await deployment_service.deploy_project(config=deployment_config, deployment_id=deployment_id)
            print(f"Deployment {deployment_id} completed successfully")
            
            # Return success result for Celery result backend
            return {
                "status": "SUCCESS",
                "deployment_id": deployment_id,
                "message": "Deployment completed successfully"
            }
            
        except asyncio.TimeoutError:
            raise Exception("Deployment timed out - service took too long to become healthy")
        
    except SoftTimeLimitExceeded:
        error_msg = f"Deployment {deployment_id} exceeded soft time limit (18 minutes) - terminating"
        print(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        print(f"Deployment {deployment_id} failed with error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        
        # Update deployment status to failed
        try:
            deployment = await prisma_client.deployment.find_unique(
                where={"id": deployment_id},
                include={"environment": True}
            )
            if deployment:
                current_logs = deployment.logs or ""
                error_msg = f"\n\n❌ Error: {str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
                await prisma_client.deployment.update(
                    where={"id": deployment_id},
                    data={
                        "status": DeploymentStatus.FAILED,
                        "logs": f"{current_logs}{error_msg}"
                    }
                )
                print(f"Updated deployment {deployment_id} status to failed")
                
                # Also update environment status if this deployment was for an environment
                if deployment.environmentId and deployment.environment:
                    # Check if there are any other active deployments for this environment
                    active_deployment = await prisma_client.deployment.find_first(
                        where={
                            "environmentId": deployment.environmentId,
                            "id": {"not": deployment_id},
                            "status": {"in": [
                                DeploymentStatus.PENDING,
                                DeploymentStatus.BUILDING, 
                                DeploymentStatus.PUSHING,
                                DeploymentStatus.PROVISIONING,
                                DeploymentStatus.DEPLOYING
                            ]}
                        }
                    )
                    
                    if not active_deployment:
                        await prisma_client.environment.update(
                            where={"id": deployment.environmentId},
                            data={"status": ProjectStatus.FAILED}
                        )
                        print(f"Updated environment {deployment.environmentId} status to FAILED")
                        
        except Exception as db_error:
            print(f"Failed to update deployment/environment status in database: {str(db_error)}")
        
        # No retries - just fail the task
        print(f"Deployment {deployment_id} failed - no retries")
        raise
    finally:
        # Skip ALL Prisma disconnects to prevent hanging - process cleanup handles it
        # Note: Both local and global Prisma disconnects can hang in Celery worker environment
        print(f"Task {self.request.id} for deployment {deployment_id} finished")


@app.task(name="abort_deployment")
def abort_deployment(deployment_id: str):
    """
    Abort an in-progress deployment.
    
    Args:
        deployment_id: ID of the deployment to abort
    """
    return asyncio.run(_abort_deployment_async(deployment_id))


async def _abort_deployment_async(deployment_id: str):
    """Async implementation of abort logic."""
    if not prisma.is_connected():
        await prisma.connect()
    
    try:
        deployment = await prisma.deployment.find_unique(where={"id": deployment_id})
        if not deployment:
            return {"success": False, "error": "Deployment not found"}
        
        if deployment.status not in [
            DeploymentStatus.PENDING,
            DeploymentStatus.BUILDING,
            DeploymentStatus.PUSHING, 
            DeploymentStatus.PROVISIONING,
            DeploymentStatus.DEPLOYING
        ]:
            return {"success": False, "error": f"Deployment is {deployment.status}, cannot abort"}
        
        # Revoke the celery task if it exists
        if deployment.celeryTaskId:
            app.control.revoke(deployment.celeryTaskId, terminate=True)
        
        # Use deployment manager to abort
        from app.services.deployment_manager import deployment_manager
        success = deployment_manager.abort_deployment(deployment_id)
        
        if success:
            current_logs = deployment.logs or ""
            await prisma.deployment.update(
                where={"id": deployment_id},
                data={
                    "status": DeploymentStatus.FAILED,
                    "logs": f"{current_logs}\n\nDeployment aborted by user"
                }
            )
        
        return {"success": success}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.task(name="cleanup_old_deployments")
def cleanup_old_deployments():
    """
    Periodic task to clean up old deployment records and logs.
    """
    from datetime import datetime, timedelta
    
    return asyncio.run(_cleanup_old_deployments_async())


async def _cleanup_old_deployments_async():
    """Async implementation of cleanup logic."""
    if not prisma.is_connected():
        await prisma.connect()
    
    try:
        # Delete deployments older than 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Count deployments to delete
        count = await prisma.deployment.count(
            where={
                "created_at": {"lt": cutoff_date},
                "status": {"in": [DeploymentStatus.SUCCESS, DeploymentStatus.FAILED]}
            }
        )
        
        # Delete in batches
        if count > 0:
            await prisma.deployment.delete_many(
                where={
                    "created_at": {"lt": cutoff_date},
                    "status": {"in": [DeploymentStatus.SUCCESS, DeploymentStatus.FAILED]}
                }
            )
        
        return {"deleted": count}
        
    except Exception as e:
        return {"error": str(e), "deleted": 0}


# Signal handlers for monitoring
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extras):
    """Log task start."""
    if task.name == "deploy_project" and kwargs:
        deployment_id = kwargs.get("deployment_id")
        print(f"Starting deployment task {task_id} for deployment {deployment_id}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extras):
    """Log task completion."""
    if task.name == "deploy_project" and kwargs:
        deployment_id = kwargs.get("deployment_id")
        print(f"Completed deployment task {task_id} for deployment {deployment_id} with state {state}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extras):
    """Log task failure."""
    if sender.name == "deploy_project" and kwargs:
        deployment_id = kwargs.get("deployment_id")
        print(f"Failed deployment task {task_id} for deployment {deployment_id}: {exception}")
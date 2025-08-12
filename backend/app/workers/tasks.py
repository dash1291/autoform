"""Celery tasks for deployment operations."""

import os
import sys
import asyncio
import signal
import traceback
import gc
from datetime import datetime, timedelta
from typing import Dict, Any
from celery import Task
from celery.signals import task_prerun, task_postrun, task_failure
from celery.exceptions import SoftTimeLimitExceeded
from sqlmodel import select

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Fix for subprocess issues in Celery workers
if not hasattr(sys.stdout, 'fileno'):
    sys.stdout = sys.__stdout__
if not hasattr(sys.stderr, 'fileno'):
    sys.stderr = sys.__stderr__

from app.workers.celery_app import app
from core.database import get_async_session
from models.deployment import Deployment, DeploymentStatus
from models.project import ProjectStatus
from models.environment import Environment as EnvironmentModel
from services.deployment import DeploymentConfig, DeploymentService
from services.deployment_manager import deployment_manager


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
    # Using SQLModel for database operations
    
    session = None
    try:
        print(f"Starting deployment task for {deployment_id} (timeout: 18 minutes)")
        
        # Connect to database
        # Database connection handled by SQLModel session
        print("Connected to database")
        
        # Update deployment status to in_progress
        async with get_async_session() as session:
            deployment = await session.get(Deployment, deployment_id)
            if not deployment:
                raise ValueError(f"Deployment {deployment_id} not found")
            
            # Update deployment status
            deployment.status = DeploymentStatus.DEPLOYING
            deployment.celery_task_id = self.request.id
            deployment.logs = "🚀 Deployment task started by Celery worker...\n"
            session.add(deployment)
            await session.commit()
        print(f"Updated deployment {deployment_id} status to DEPLOYING")
        
        # Create DeploymentConfig from dict
        deployment_config = DeploymentConfig(**config)
        print(f"Created deployment config for project {deployment_config.project_id}")
        
        # SQLModel doesn't need explicit connection management
        
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
        print(f"Full traceback: {traceback.format_exc()}")
        
        # Update deployment status to failed
        try:
            async with get_async_session() as error_session:
                deployment = await error_session.get(Deployment, deployment_id)
                if deployment:
                    current_logs = deployment.logs or ""
                    error_msg = f"\n\n❌ Error: {str(e)}"
                    
                    # Update deployment status to failed
                    deployment.status = DeploymentStatus.FAILED
                    deployment.logs = f"{current_logs}{error_msg}"
                    error_session.add(deployment)
                    await error_session.commit()
                    print(f"Updated deployment {deployment_id} status to failed")
                    
                    # Also update environment status if this deployment was for an environment  
                    if deployment.environment_id:
                        # Check if there are any other active deployments for this environment
                        
                        result = await error_session.execute(
                            select(Deployment).where(
                                (Deployment.environment_id == deployment.environment_id) &
                                (Deployment.id != deployment_id) &
                                (Deployment.status.in_([
                                    DeploymentStatus.PENDING,
                                    DeploymentStatus.BUILDING, 
                                    DeploymentStatus.PUSHING,
                                    DeploymentStatus.PROVISIONING,
                                    DeploymentStatus.DEPLOYING
                                ]))
                            )
                        )
                        active_deployment = result.scalar_one_or_none()
                        
                        if not active_deployment:
                            environment = await error_session.get(EnvironmentModel, deployment.environment_id)
                            if environment:
                                environment.status = ProjectStatus.FAILED
                                error_session.add(environment)
                                await error_session.commit()
                                print(f"Updated environment {deployment.environment_id} status to FAILED")
                        
        except Exception as db_error:
            print(f"Failed to update deployment/environment status in database: {str(db_error)}")
        
        # No retries - just fail the task
        print(f"Deployment {deployment_id} failed - no retries")
        raise
    finally:
        # Ensure all async resources are properly cleaned up
        try:
            gc.collect()  # Force garbage collection to clean up async resources
        except Exception as cleanup_error:
            print(f"Cleanup error (non-critical): {cleanup_error}")
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
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(Deployment).where(Deployment.id == deployment_id)
            )
            deployment = result.scalar_one_or_none()
            
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
            if deployment.celery_task_id:
                app.control.revoke(deployment.celery_task_id, terminate=True)
            
            # Use deployment manager to abort
            success = deployment_manager.abort_deployment(deployment_id)
            
            if success:
                current_logs = deployment.logs or ""
                deployment.status = DeploymentStatus.FAILED
                deployment.logs = f"{current_logs}\n\nDeployment aborted by user"
                session.add(deployment)
                await session.commit()
            
            return {"success": success}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.task(name="cleanup_old_deployments")
def cleanup_old_deployments():
    """
    Periodic task to clean up old deployment records and logs.
    """
    return asyncio.run(_cleanup_old_deployments_async())


async def _cleanup_old_deployments_async():
    """Async implementation of cleanup logic."""
    try:
        async with get_async_session() as session:
            # Delete deployments older than 30 days
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            # Get deployments to delete
            result = await session.execute(
                select(Deployment).where(
                    (Deployment.created_at < cutoff_date) &
                    (Deployment.status.in_([DeploymentStatus.SUCCESS, DeploymentStatus.FAILED]))
                )
            )
            deployments_to_delete = result.all()
            count = len(deployments_to_delete)
            
            # Delete in batches
            if count > 0:
                for deployment in deployments_to_delete:
                    await session.delete(deployment)
                await session.commit()
            
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
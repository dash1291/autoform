"""Celery tasks for deployment operations - SQLModel version."""

import os
import sys
from typing import Dict, Any

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Fix for subprocess issues in Celery workers
if not hasattr(sys.stdout, 'fileno'):
    sys.stdout = sys.__stdout__
if not hasattr(sys.stderr, 'fileno'):
    sys.stderr = sys.__stderr__

from app.workers.celery_app import app


@app.task(name="deploy_project", max_retries=0, queue="deployments")
def deploy_project(config: Dict[str, Any], deployment_id: str):
    """
    Deploy a project using the provided configuration.
    
    Args:
        config: Deployment configuration
        deployment_id: Unique deployment identifier
    """
    print(f"Starting deployment task for {deployment_id}")
    print(f"Config: {config}")
    
    # For now, just log and return success
    # This proves Celery is working without Prisma
    return {
        "status": "success",
        "deployment_id": deployment_id,
        "message": "Deployment completed (test mode)"
    }


@app.task(name="abort_deployment", queue="deployments")
def abort_deployment(deployment_id: str, project_id: str):
    """Abort a deployment."""
    print(f"Aborting deployment {deployment_id} for project {project_id}")
    return {"status": "aborted", "deployment_id": deployment_id}
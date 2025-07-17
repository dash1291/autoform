"""Monitoring utilities for Celery tasks and deployments."""

import asyncio
from typing import Dict, Any, Optional
from celery import states
from app.workers.celery_app import app
from core.database import get_async_session
from models.deployment import Deployment
from sqlmodel import select


async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a Celery task."""
    result = app.AsyncResult(task_id)
    
    return {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
        "failed": result.failed() if result.ready() else None,
        "info": result.info if result.status != states.PENDING else None,
    }


async def get_deployment_status(deployment_id: str) -> Dict[str, Any]:
    """Get deployment status including Celery task status."""
    # SQLModel handles connections automatically
    
    async with get_async_session() as session:
        result = await session.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        deployment = result.scalar_one_or_none()
    
    if not deployment:
        return {"error": "Deployment not found"}
    
    response = {
        "deployment_id": deployment.id,
        "status": deployment.status,
        "created_at": deployment.created_at.isoformat() if deployment.created_at else None,
        "updated_at": deployment.updated_at.isoformat() if deployment.updated_at else None,
        "environment_id": deployment.environment_id,
    }
    
    # Add Celery task status if available
    if deployment.celery_task_id:
        task_status = await get_task_status(deployment.celery_task_id)
        response["task"] = task_status
    
    return response


async def list_active_tasks() -> Dict[str, Any]:
    """List all active Celery tasks."""
    inspect = app.control.inspect()
    
    # Get active tasks
    active = inspect.active()
    scheduled = inspect.scheduled()
    reserved = inspect.reserved()
    
    return {
        "active": active,
        "scheduled": scheduled,
        "reserved": reserved,
    }


async def get_worker_stats() -> Dict[str, Any]:
    """Get statistics about Celery workers."""
    inspect = app.control.inspect()
    
    # Get worker stats
    stats = inspect.stats()
    registered = inspect.registered()
    
    return {
        "stats": stats,
        "registered_tasks": registered,
        "workers": list(stats.keys()) if stats else [],
    }


# CLI utility for monitoring
if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python monitoring.py <command> [args]")
            print("Commands:")
            print("  task <task_id> - Get task status")
            print("  deployment <deployment_id> - Get deployment status")
            print("  active - List active tasks")
            print("  workers - Get worker stats")
            return
        
        command = sys.argv[1]
        
        if command == "task" and len(sys.argv) >= 3:
            result = await get_task_status(sys.argv[2])
            print(result)
        elif command == "deployment" and len(sys.argv) >= 3:
            result = await get_deployment_status(sys.argv[2])
            print(result)
        elif command == "active":
            result = await list_active_tasks()
            print(result)
        elif command == "workers":
            result = await get_worker_stats()
            print(result)
        else:
            print("Invalid command")
    
    asyncio.run(main())
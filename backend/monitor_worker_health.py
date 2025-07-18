#!/usr/bin/env python3
"""
Monitor Celery worker health and detect stuck tasks
"""
import sys
sys.path.insert(0, '.')

import asyncio
from datetime import datetime, timedelta
from app.workers.celery_app import app
from core.database import get_async_session
from models.deployment import Deployment, DeploymentStatus
from sqlmodel import select, and_

async def monitor_worker_health():
    """Monitor worker health and detect stuck deployments"""
    
    print("=== CELERY WORKER HEALTH MONITOR ===\n")
    
    # Check Celery worker status
    i = app.control.inspect()
    
    # Get different task states
    active = i.active()
    scheduled = i.scheduled()
    reserved = i.reserved()
    
    print("📊 CELERY QUEUE STATUS:")
    active_count = sum(len(tasks) for tasks in (active or {}).values())
    scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
    reserved_count = sum(len(tasks) for tasks in (reserved or {}).values())
    
    print(f"  • Active tasks: {active_count}")
    print(f"  • Scheduled tasks: {scheduled_count}")
    print(f"  • Reserved tasks: {reserved_count}")
    
    if active_count == 0:
        print("  ✅ No active tasks - worker is ready")
    else:
        print("  ⚠️  Worker is busy with tasks")
        if active:
            for worker, tasks in active.items():
                for task in tasks:
                    print(f"    - {task['id'][:8]}... ({task['name']})")
    
    print()
    
    # Check database for stuck deployments
    async with get_async_session() as session:
        try:
            # Check for deployments that might be stuck
            cutoff_time = datetime.utcnow() - timedelta(minutes=20)  # 20 min = our task timeout
            
            result = await session.execute(
                select(Deployment).where(
                    and_(
                        Deployment.status.in_([
                            DeploymentStatus.PENDING, 
                            DeploymentStatus.DEPLOYING, 
                            DeploymentStatus.BUILDING, 
                            DeploymentStatus.PUSHING, 
                            DeploymentStatus.PROVISIONING
                        ]),
                        Deployment.created_at < cutoff_time
                    )
                ).order_by(Deployment.created_at.desc())
            )
            stuck_deployments = result.all()
            
            print("📋 DATABASE STATUS:")
            if stuck_deployments:
                print(f"  ⚠️  Found {len(stuck_deployments)} potentially stuck deployments:")
                for deployment in stuck_deployments:
                    age_minutes = (datetime.utcnow() - deployment.created_at).total_seconds() / 60
                    print(f"    - {deployment.id[:8]}... (status: {deployment.status}, age: {age_minutes:.1f}min)")
                    if deployment.celery_task_id:
                        print(f"      Task ID: {deployment.celery_task_id[:8]}...")
            else:
                print("  ✅ No stuck deployments found")
            
            # Check recent deployments
            recent_result = await session.execute(
                select(Deployment).where(
                    Deployment.created_at >= datetime.utcnow() - timedelta(hours=1)
                ).order_by(Deployment.created_at.desc()).limit(5)
            )
            recent_deployments = recent_result.all()
            
            print(f"\n📈 RECENT ACTIVITY (last hour):")
            if recent_deployments:
                status_counts = {}
                for deployment in recent_deployments:
                    status_counts[deployment.status] = status_counts.get(deployment.status, 0) + 1
                
                for status, count in status_counts.items():
                    print(f"  • {status}: {count}")
            else:
                print("  • No recent deployments")
                
        except Exception as e:
            print(f"  ❌ Database error: {e}")

def check_worker_responsiveness():
    """Check if worker is responsive"""
    print("\n🔍 WORKER RESPONSIVENESS:")
    
    try:
        # Try to ping workers
        ping_result = app.control.ping(timeout=5)
        if ping_result:
            # ping_result is a list of worker responses
            for worker_response in ping_result:
                for worker, response in worker_response.items():
                    if response.get('ok') == 'pong':
                        print(f"  ✅ {worker}: responsive")
                    else:
                        print(f"  ❌ {worker}: not responding")
        else:
            print("  ❌ No workers responding to ping")
    except Exception as e:
        print(f"  ❌ Error pinging workers: {e}")

if __name__ == "__main__":
    print(f"Monitor started at {datetime.now().isoformat()}\n")
    
    # Check worker responsiveness
    check_worker_responsiveness()
    
    # Check worker health
    asyncio.run(monitor_worker_health())
    
    print(f"\n✅ Health check completed at {datetime.now().isoformat()}")
#!/usr/bin/env python3
"""
Quick test script to verify Celery tasks are working
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.getcwd())

from app.workers.tasks import deploy_project
from app.workers.celery_app import app

def test_celery_connection():
    """Test if Celery can connect to Redis"""
    try:
        # Check if we can connect to the broker
        inspector = app.control.inspect()
        active_tasks = inspector.active()
        print("✅ Celery connection successful")
        print(f"Active workers: {list(active_tasks.keys()) if active_tasks else 'None'}")
        return True
    except Exception as e:
        print(f"❌ Celery connection failed: {e}")
        return False

def test_task_import():
    """Test if tasks can be imported"""
    try:
        from app.workers.tasks import deploy_project, abort_deployment, cleanup_old_deployments
        print("✅ Tasks imported successfully")
        return True
    except Exception as e:
        print(f"❌ Task import failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Celery setup...")
    print("-" * 40)
    
    test_task_import()
    test_celery_connection()
    
    print("-" * 40)
    print("Test complete!")
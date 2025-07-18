#!/usr/bin/env python
"""Debug Celery configuration and connection"""

import os
import sys

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.workers.celery_app import app
from app.workers.tasks_simple import deploy_project

print("=== Celery Debug Info ===")
print(f"Broker URL: {app.conf.broker_url}")
print(f"Result Backend: {app.conf.result_backend}")
print(f"Task Routes: {app.conf.task_routes}")
print(f"Task Queues: {app.conf.task_queues}")

# Check if we can connect
try:
    # This will raise an exception if it can't connect
    stats = app.control.inspect().stats()
    if stats:
        print("\n✅ Connected to Celery broker")
        print(f"Workers found: {list(stats.keys())}")
    else:
        print("\n❌ No workers found")
except Exception as e:
    print(f"\n❌ Failed to connect to broker: {e}")

# Check registered tasks
try:
    registered = app.control.inspect().registered()
    if registered:
        print("\n=== Registered Tasks ===")
        for worker, tasks in registered.items():
            print(f"\nWorker: {worker}")
            for task in tasks:
                print(f"  - {task}")
except Exception as e:
    print(f"\n❌ Failed to get registered tasks: {e}")

# Test queuing a simple task
print("\n=== Testing Task Queue ===")
try:
    # Create a minimal test config
    test_config = {
        "project_id": "test",
        "project_name": "test",
        "git_repo_url": "https://github.com/test/test",
        "branch": "main",
        "commit_sha": "test123",
        "aws_region": "us-east-1"
    }
    
    # Try to queue a task
    result = deploy_project.apply_async(
        kwargs={
            "config": test_config,
            "deployment_id": "test-deployment"
        },
        queue="deployments"
    )
    print(f"✅ Task queued successfully: {result.id}")
    
    # Check if it's in the queue
    import redis
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    queue_length = r.llen("deployments")
    print(f"Queue 'deployments' length: {queue_length}")
    
except Exception as e:
    print(f"❌ Failed to queue task: {e}")
    import traceback
    traceback.print_exc()
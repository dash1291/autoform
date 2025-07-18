#!/usr/bin/env python3
"""
Manage Celery tasks - inspect and revoke stuck tasks
"""
import sys
sys.path.insert(0, '.')

from app.workers.celery_app import app

def list_active_tasks():
    """List all active tasks"""
    i = app.control.inspect()
    
    # Get different task states
    active = i.active()
    scheduled = i.scheduled()
    reserved = i.reserved()
    
    print("=== ACTIVE TASKS ===")
    if active:
        for worker, tasks in active.items():
            print(f"\nWorker: {worker}")
            for task in tasks:
                print(f"  ID: {task['id']}")
                print(f"  Name: {task['name']}")
                print(f"  Args: {task.get('args', [])}")
                print(f"  ---")
    else:
        print("No active tasks")
    
    print("\n=== SCHEDULED TASKS ===")
    if scheduled:
        for worker, tasks in scheduled.items():
            print(f"\nWorker: {worker}")
            for task in tasks:
                print(f"  ID: {task['request']['id']}")
                print(f"  Name: {task['request']['name']}")
                print(f"  ETA: {task.get('eta', 'N/A')}")
                print(f"  ---")
    else:
        print("No scheduled tasks")
    
    print("\n=== RESERVED TASKS ===")
    if reserved:
        for worker, tasks in reserved.items():
            print(f"\nWorker: {worker}")
            for task in tasks:
                print(f"  ID: {task['id']}")
                print(f"  Name: {task['name']}")
                print(f"  ---")
    else:
        print("No reserved tasks")

def revoke_task(task_id):
    """Revoke a specific task"""
    app.control.revoke(task_id, terminate=True)
    print(f"Revoked task: {task_id}")

def revoke_all_tasks():
    """Revoke all active tasks"""
    i = app.control.inspect()
    active = i.active()
    
    if not active:
        print("No active tasks to revoke")
        return
    
    for worker, tasks in active.items():
        for task in tasks:
            task_id = task['id']
            app.control.revoke(task_id, terminate=True)
            print(f"Revoked task: {task_id}")

def purge_queue():
    """Purge all pending tasks from the queue"""
    app.control.purge()
    print("Purged all pending tasks from queue")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage Celery tasks")
    parser.add_argument("command", choices=["list", "revoke", "revoke-all", "purge"],
                        help="Command to execute")
    parser.add_argument("--task-id", help="Task ID for revoke command")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_active_tasks()
    elif args.command == "revoke":
        if not args.task_id:
            print("Error: --task-id required for revoke command")
            sys.exit(1)
        revoke_task(args.task_id)
    elif args.command == "revoke-all":
        revoke_all_tasks()
    elif args.command == "purge":
        response = input("This will delete ALL pending tasks. Are you sure? (yes/no): ")
        if response.lower() == "yes":
            purge_queue()
        else:
            print("Cancelled")
"""Celery application configuration for deployment workers."""

import os
from celery import Celery

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
app = Celery(
    "autoform",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.tasks"]
)

# Celery configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Only take one task at a time
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks (was 1, too aggressive)
    worker_hijack_root_logger=False,
    worker_log_color=False,
    worker_disable_rate_limits=True,  # Disable rate limiting for faster task pickup
    
    # Task execution limits (aligned with deployment service timeout)
    task_time_limit=1200,  # 20 minutes hard limit (15 min deploy + 5 min buffer)
    task_soft_time_limit=1080,  # 18 minutes soft limit
    task_acks_late=True,  # Acknowledge tasks only after completion to ensure reliability
    task_reject_on_worker_lost=True,  # Reject tasks if worker dies
    
    # Result backend
    result_expires=86400,  # 24 hours
    
    # Retry settings - disabled
    task_default_retry_delay=60,
    task_max_retries=0,
)

if __name__ == "__main__":
    app.start()
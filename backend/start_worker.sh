#!/bin/bash

# Start Celery worker for deployment tasks

echo "Starting Celery worker..."

# Set the Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Start the worker
celery -A app.workers.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --pool=prefork \
    -n worker@%h \
    -Q deployments,high_priority
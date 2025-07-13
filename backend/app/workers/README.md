# Celery Worker System for Deployments

This directory contains the Celery-based worker system for handling deployments asynchronously.

## Architecture

The deployment system now uses Celery workers with Redis as the message broker instead of FastAPI's background tasks. This provides:

- **Scalability**: Multiple worker processes can handle deployments in parallel
- **Reliability**: Tasks persist in Redis and survive server restarts
- **Monitoring**: Built-in task monitoring and status tracking
- **Retries**: Automatic retry on failures with exponential backoff

## Components

- `celery_app.py`: Celery application configuration
- `tasks.py`: Deployment tasks (deploy_project, abort_deployment, cleanup)
- `monitoring.py`: Utilities for monitoring task and deployment status

## Running the Worker

1. Start Redis (required):
```bash
redis-server
```

2. Start the Celery worker:
```bash
cd backend
./start_worker.sh
```

Or manually:
```bash
celery -A app.workers.celery_app worker --loglevel=info
```

## Configuration

Environment variables:
- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379/0`)

## Task Details

### deploy_project
- Deploys a project to AWS infrastructure
- Accepts deployment configuration and deployment ID
- Updates deployment status in database
- Automatic retry on failure (max 3 retries)

### abort_deployment
- Aborts an in-progress deployment
- Revokes the Celery task if running
- Updates deployment status to "aborted"

### cleanup_old_deployments
- Periodic task to clean up old deployment records
- Deletes deployments older than 30 days

## Monitoring

Use the monitoring script to check deployment status:

```bash
# Check specific task status
python app/workers/monitoring.py task <task_id>

# Check deployment status
python app/workers/monitoring.py deployment <deployment_id>

# List active tasks
python app/workers/monitoring.py active

# Get worker statistics
python app/workers/monitoring.py workers
```

## API Changes

The deployment endpoints now queue tasks instead of running them directly:

- `POST /environments/{environment_id}/deploy` - Queues deployment task
- `POST /{deployment_id}/abort` - Queues abort task
- Webhook deployments also use the queue system

## Troubleshooting

1. **Worker not processing tasks**: Check Redis is running and accessible
2. **Tasks stuck**: Use monitoring tools to check task status
3. **Deployment failures**: Check worker logs and deployment logs in database
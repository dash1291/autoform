# Docker Setup for Autoform Backend

This guide explains how to run the Autoform backend with all its services using Docker Compose.

## Services

The docker-compose.yml file includes:

1. **PostgreSQL** - Database
2. **Redis** - Message broker for Celery
3. **Backend API** - FastAPI application
4. **Celery Worker** - Processes deployment tasks
5. **Celery Beat** - Scheduled tasks (optional)
6. **Flower** - Celery monitoring UI (optional)

## Quick Start

1. **Copy environment variables:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` file with your credentials:**
   - AWS credentials (required for deployments)
   - GitHub OAuth credentials (required for authentication)
   - Generate secure keys for SECRET_KEY and ENCRYPTION_KEY

3. **Start all services:**
   ```bash
   docker-compose up -d
   ```

4. **Check service status:**
   ```bash
   docker-compose ps
   ```

5. **View logs:**
   ```bash
   # All services
   docker-compose logs -f
   
   # Specific service
   docker-compose logs -f backend
   docker-compose logs -f celery-worker
   ```

## Service URLs

- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Flower (Celery monitoring)**: http://localhost:5555

## Development

For development with hot-reload:
```bash
docker-compose up
```

The `docker-compose.override.yml` file automatically enables:
- Hot reload for the backend
- Debug logging
- Volume mounts for code changes

## Production

For production, use only the base docker-compose.yml:
```bash
docker-compose -f docker-compose.yml up -d
```

## Database Migrations

Run Prisma migrations:
```bash
docker-compose exec backend rye run prisma migrate dev
```

Generate Prisma client:
```bash
docker-compose exec backend rye run prisma generate
```

## Monitoring Deployments

1. **Using Flower UI:**
   Visit http://localhost:5555 to see:
   - Active tasks
   - Task history
   - Worker status

2. **Using CLI:**
   ```bash
   # Check worker logs
   docker-compose logs -f celery-worker
   
   # Execute monitoring script
   docker-compose exec celery-worker python app/workers/monitoring.py active
   ```

## Troubleshooting

1. **Services not starting:**
   - Check `.env` file exists and has required variables
   - Ensure ports 5432, 6379, 8000, 5555 are not in use

2. **Database connection errors:**
   - Wait for PostgreSQL to be fully ready
   - Check DATABASE_URL in .env

3. **Celery not processing tasks:**
   - Check Redis is running: `docker-compose ps redis`
   - Check worker logs: `docker-compose logs celery-worker`

4. **AWS deployment errors:**
   - Verify AWS credentials in .env
   - Check AWS_REGION is correct

## Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: Deletes data!)
docker-compose down -v
```

## Scaling Workers

To run multiple Celery workers:
```bash
docker-compose up -d --scale celery-worker=3
```

## Environment Variables

See `.env.example` for all available environment variables and their descriptions.
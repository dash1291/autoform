# Backend Dockerfile for Autoform
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY requirements.lock ./

# Install Python dependencies using pip
RUN pip install --no-cache-dir -r requirements.lock

# Copy application code
COPY . .

# Generate Prisma client
RUN prisma generate

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONTHREADPOOLSIZE=20

# Expose port
EXPOSE 8000

# Start command - production configuration with reduced workers for Supabase pooler
# Reduced to 2 workers to prevent connection pool exhaustion (2 workers × 3 pool = 6 connections)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "asyncio", "--access-log", "--log-level", "info"]
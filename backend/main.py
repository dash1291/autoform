from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import asyncio
import concurrent.futures

from core.config import settings
from app.routers import (
    projects,
    auth,
    deployments,
    environment_variables,
    github,
    debug,
    aws,
    webhook,
    teams,
    environments,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")

    # Configure increased thread pool for background tasks
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=20)
    loop.set_default_executor(executor)
    logger.info(f"Thread pool configured with 20 max workers")

    # Initialize database connection
    from core.database import prisma

    await prisma.connect()

    yield

    # Shutdown
    logger.info("Shutting down...")
    await prisma.disconnect()
    executor.shutdown(wait=True)
    logger.info("Thread pool shut down")


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(deployments.router, prefix="/api/deployments", tags=["deployments"])
app.include_router(
    environment_variables.router,
    prefix="/api/environments/{environment_id}/environment-variables",
    tags=["environment-variables"],
)
app.include_router(github.router, prefix="/api/github", tags=["github"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])
app.include_router(aws.router, prefix="/api/aws", tags=["aws"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["webhook"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(
    environments.router, prefix="/api/environments", tags=["environments"]
)


@app.get("/")
async def root():
    return {"message": "AutoForm Backend API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

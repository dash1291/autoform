from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from contextlib import asynccontextmanager
import logging

from core.config import settings
from app.routers import projects, auth, deployments, environment_variables, github, debug, aws, webhook, teams

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure redirects preserve HTTPS protocol"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Check if this is a redirect response
        if response.status_code in (301, 302, 307, 308):
            location = response.headers.get("location")
            if location and location.startswith("http://"):
                # Get the original request scheme
                forwarded_proto = request.headers.get("x-forwarded-proto")
                if forwarded_proto == "https" or request.url.scheme == "https":
                    # Replace http:// with https://
                    new_location = location.replace("http://", "https://", 1)
                    response.headers["location"] = new_location
                    logger.info(f"Redirected HTTPS preserve: {location} -> {new_location}")
        
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    # Initialize database connection
    from core.database import prisma
    await prisma.connect()
    yield
    # Shutdown
    logger.info("Shutting down...")
    await prisma.disconnect()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan
)

# Add HTTPS redirect middleware first
app.add_middleware(HTTPSRedirectMiddleware)

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
    prefix="/api/projects/{project_id}/environment-variables",
    tags=["environment-variables"]
)
app.include_router(github.router, prefix="/api/github", tags=["github"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])
app.include_router(aws.router, prefix="/api/aws", tags=["aws"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["webhook"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])


@app.get("/")
async def root():
    return {"message": "AutoForm Backend API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
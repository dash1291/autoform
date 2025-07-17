from sqlmodel import Session, create_engine, SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://autoform:autoform123@localhost:5432/autoform")

# Convert to async URL if needed
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = DATABASE_URL

# Create async engine
engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, future=True)

# Create async session factory
async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Function to get async DB session
async def get_session():
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

# Direct session context manager for use in non-dependency contexts
def get_async_session():
    return async_session_factory()

# Create tables
async def create_db_and_tables():
    # Import all models to ensure they're registered
    from models.user import User, Account, Session, VerificationToken, UserAWSConfig
    from models.team import Team, TeamMember, TeamAwsConfig
    from models.project import Project
    from models.environment import Environment, EnvironmentVariable
    from models.deployment import Deployment
    from models.webhook import Webhook
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

# Legacy compatibility - create a "db" object that mimics Prisma interface
class Database:
    def __init__(self):
        self._session = None
    
    async def connect(self):
        """Connect to database - for compatibility"""
        pass
    
    async def disconnect(self):
        """Disconnect from database - for compatibility"""
        pass
    
    def is_connected(self):
        """Check if connected - for compatibility"""
        return True

# Create a global db instance for compatibility
db = Database()

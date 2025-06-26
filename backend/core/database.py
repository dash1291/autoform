from prisma import Prisma
from prisma.errors import PrismaError
import logging

logger = logging.getLogger(__name__)

# Create a single instance of Prisma client
prisma = Prisma()


async def get_db():
    """
    Dependency to get database connection
    """
    if not prisma.is_connected():
        await prisma.connect()
    return prisma


async def disconnect_db():
    """
    Disconnect from database
    """
    if prisma.is_connected():
        await prisma.disconnect()

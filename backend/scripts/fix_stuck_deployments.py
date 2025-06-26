"""
Script to fix stuck deployments and environments
Run this to clean up deployments that are stuck in DEPLOYING status
"""
import asyncio
import logging
from datetime import datetime, timedelta
from core.database import prisma
from schemas import DeploymentStatus, ProjectStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_stuck_deployments():
    """Find and fix deployments stuck in deploying status"""
    await prisma.connect()
    
    try:
        # Find deployments that have been in deploying status for more than 30 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        
        stuck_deployments = await prisma.deployment.find_many(
            where={
                "status": {
                    "in": [
                        DeploymentStatus.PENDING,
                        DeploymentStatus.BUILDING,
                        DeploymentStatus.PUSHING,
                        DeploymentStatus.PROVISIONING,
                        DeploymentStatus.DEPLOYING,
                    ]
                },
                "createdAt": {"lt": cutoff_time}
            },
            include={"environment": True}
        )
        
        logger.info(f"Found {len(stuck_deployments)} stuck deployments")
        
        for deployment in stuck_deployments:
            logger.info(f"Fixing deployment {deployment.id} (status: {deployment.status}, created: {deployment.createdAt})")
            
            # Update deployment to failed
            await prisma.deployment.update(
                where={"id": deployment.id},
                data={
                    "status": DeploymentStatus.FAILED,
                    "logs": (deployment.logs or "") + "\n[SYSTEM] Deployment timed out and was marked as failed"
                }
            )
            
            # Update environment status if needed
            if deployment.environmentId and deployment.environment:
                # Check if there are any other active deployments for this environment
                active_deployment = await prisma.deployment.find_first(
                    where={
                        "environmentId": deployment.environmentId,
                        "id": {"not": deployment.id},
                        "status": {
                            "in": [
                                DeploymentStatus.PENDING,
                                DeploymentStatus.BUILDING,
                                DeploymentStatus.PUSHING,
                                DeploymentStatus.PROVISIONING,
                                DeploymentStatus.DEPLOYING,
                            ]
                        }
                    }
                )
                
                if not active_deployment:
                    logger.info(f"Updating environment {deployment.environmentId} status to FAILED")
                    await prisma.environment.update(
                        where={"id": deployment.environmentId},
                        data={"status": ProjectStatus.FAILED}
                    )
        
        # Also check for environments stuck in DEPLOYING status
        stuck_environments = await prisma.environment.find_many(
            where={
                "status": ProjectStatus.DEPLOYING,
                "updatedAt": {"lt": cutoff_time}
            }
        )
        
        logger.info(f"Found {len(stuck_environments)} environments stuck in DEPLOYING status")
        
        for environment in stuck_environments:
            # Check if there are any active deployments
            active_deployment = await prisma.deployment.find_first(
                where={
                    "environmentId": environment.id,
                    "status": {
                        "in": [
                            DeploymentStatus.PENDING,
                            DeploymentStatus.BUILDING,
                            DeploymentStatus.PUSHING,
                            DeploymentStatus.PROVISIONING,
                            DeploymentStatus.DEPLOYING,
                        ]
                    }
                }
            )
            
            if not active_deployment:
                logger.info(f"Updating environment {environment.id} status to FAILED (no active deployments)")
                await prisma.environment.update(
                    where={"id": environment.id},
                    data={"status": ProjectStatus.FAILED}
                )
                
        logger.info("Cleanup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise
    finally:
        await prisma.disconnect()


if __name__ == "__main__":
    asyncio.run(fix_stuck_deployments())
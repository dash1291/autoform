"""
Script to fix stuck deployments and environments
Run this to clean up deployments that are stuck in DEPLOYING status
"""
import asyncio
import logging
from datetime import datetime, timedelta
from core.database import get_async_session
from models.deployment import Deployment, DeploymentStatus
from models.project import ProjectStatus
from models.environment import Environment
from sqlmodel import select, and_

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_stuck_deployments():
    """Find and fix deployments stuck in deploying status"""
    
    try:
        # Find deployments that have been in deploying status for more than 30 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        
        async with get_async_session() as session:
            # Find stuck deployments
            result = await session.execute(
                select(Deployment).where(
                    and_(
                        Deployment.status.in_([
                            DeploymentStatus.PENDING,
                            DeploymentStatus.BUILDING,
                            DeploymentStatus.PUSHING,
                            DeploymentStatus.PROVISIONING,
                            DeploymentStatus.DEPLOYING,
                        ]),
                        Deployment.created_at < cutoff_time
                    )
                )
            )
            stuck_deployments = result.all()
            
            logger.info(f"Found {len(stuck_deployments)} stuck deployments")
            
            for deployment in stuck_deployments:
                logger.info(f"Fixing deployment {deployment.id} (status: {deployment.status}, created: {deployment.created_at})")
                
                # Update deployment to failed
                deployment.status = DeploymentStatus.FAILED
                deployment.logs = (deployment.logs or "") + "\n[SYSTEM] Deployment timed out and was marked as failed"
                session.add(deployment)
                
                # Update environment status if needed
                if deployment.environment_id:
                    # Check if there are any other active deployments for this environment
                    active_result = await session.execute(
                        select(Deployment).where(
                            and_(
                                Deployment.environment_id == deployment.environment_id,
                                Deployment.id != deployment.id,
                                Deployment.status.in_([
                                    DeploymentStatus.PENDING,
                                    DeploymentStatus.BUILDING,
                                    DeploymentStatus.PUSHING,
                                    DeploymentStatus.PROVISIONING,
                                    DeploymentStatus.DEPLOYING,
                                ])
                            )
                        )
                    )
                    active_deployment = active_result.scalar_one_or_none()
                    
                    if not active_deployment:
                        logger.info(f"Updating environment {deployment.environment_id} status to FAILED")
                        environment = await session.get(Environment, deployment.environment_id)
                        if environment:
                            environment.status = ProjectStatus.FAILED
                            session.add(environment)
            
            # Also check for environments stuck in DEPLOYING status
            env_result = await session.execute(
                select(Environment).where(
                    and_(
                        Environment.status == ProjectStatus.DEPLOYING,
                        Environment.updated_at < cutoff_time
                    )
                )
            )
            stuck_environments = env_result.all()
            
            logger.info(f"Found {len(stuck_environments)} environments stuck in DEPLOYING status")
            
            for environment in stuck_environments:
                # Check if there are any active deployments
                active_result = await session.execute(
                    select(Deployment).where(
                        and_(
                            Deployment.environment_id == environment.id,
                            Deployment.status.in_([
                                DeploymentStatus.PENDING,
                                DeploymentStatus.BUILDING,
                                DeploymentStatus.PUSHING,
                                DeploymentStatus.PROVISIONING,
                                DeploymentStatus.DEPLOYING,
                            ])
                        )
                    )
                )
                active_deployment = active_result.scalar_one_or_none()
                
                if not active_deployment:
                    logger.info(f"Updating environment {environment.id} status to FAILED (no active deployments)")
                    environment.status = ProjectStatus.FAILED
                    session.add(environment)
            
            await session.commit()
            logger.info("Cleanup completed successfully")
                
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(fix_stuck_deployments())
#!/usr/bin/env python3
"""Test SQLModel setup"""

import asyncio
from core.database import create_db_and_tables, async_session
from models.deployment import Deployment, DeploymentStatus
from sqlmodel import select
import uuid

async def test_sqlmodel():
    """Test basic SQLModel operations"""
    
    # Create tables
    print("Creating database tables...")
    await create_db_and_tables()
    print("✅ Tables created")
    
    # Create a test deployment
    async with async_session() as session:
        deployment = Deployment(
            id=str(uuid.uuid4()),
            project_id="test-project",
            environment_id="test-env",
            status=DeploymentStatus.PENDING,
            image_tag="test:latest",
            commit_sha="abc123",
            logs="Test deployment"
        )
        
        session.add(deployment)
        await session.commit()
        print(f"✅ Created deployment: {deployment.id}")
        
        # Query it back
        result = await session.execute(
            select(Deployment).where(Deployment.id == deployment.id)
        )
        found = result.scalar_one_or_none()
        
        if found:
            print(f"✅ Found deployment: {found.id}, status: {found.status}")
        else:
            print("❌ Deployment not found")

if __name__ == "__main__":
    asyncio.run(test_sqlmodel())
#!/usr/bin/env python3
"""
Simple test to verify environment-based webhook logic
"""
import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.abspath('.'))

from core.database import prisma
from app.routers.webhook import github_webhook
from fastapi import Request, BackgroundTasks
from unittest.mock import MagicMock, patch
import json

async def test_basic_webhook_flow():
    """Test that the new environment-based webhook logic doesn't crash"""
    print("Testing basic webhook environment logic...")
    
    # Mock the request
    mock_request = MagicMock()
    mock_request.headers = {
        "X-Hub-Signature-256": "sha256=test",
        "X-GitHub-Event": "push"
    }
    
    # Mock payload
    payload_data = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/test/repo.git"},
        "commits": [{"id": "abc123", "message": "Test commit"}]
    }
    
    payload_json = json.dumps(payload_data).encode('utf-8')
    
    # Mock the async method properly
    async def mock_body():
        return payload_json
    mock_request.body = mock_body
    
    mock_background_tasks = MagicMock()
    
    # Mock database calls to return empty results (no webhook found)
    with patch('app.routers.webhook.prisma') as mock_prisma:
        # Mock the async method properly
        async def mock_find_unique(*args, **kwargs):
            return None
        mock_prisma.webhook.find_unique = mock_find_unique
        
        try:
            result = await github_webhook(mock_request, mock_background_tasks)
            print(f"Basic test passed: {result}")
            return True
        except Exception as e:
            print(f"Basic test failed: {e}")
            return False

if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_basic_webhook_flow())
    if success:
        print("Environment webhook logic appears to be working!")
    else:
        print("Environment webhook logic has issues")
        sys.exit(1)
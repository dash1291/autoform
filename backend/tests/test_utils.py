"""
Utility functions for running tests
"""
import os
import sys
import subprocess
import time
from pathlib import Path


def ensure_localstack_running():
    """Ensure LocalStack is running for integration tests"""
    try:
        # Check if LocalStack is already running
        import requests
        response = requests.get("http://localhost:4566/_localstack/health", timeout=2)
        if response.status_code == 200:
            print("LocalStack is already running")
            return True
    except:
        pass
    
    print("LocalStack not detected. Please start it with: docker-compose up -d localstack")
    return False


def run_infrastructure_tests():
    """Run infrastructure tests with proper environment setup"""
    # Set test environment variables
    os.environ["USE_LOCALSTACK"] = "false"  # Use moto by default
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    
    # Change to backend directory
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    
    # Run pytest
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/infrastructure/",
        "-v",
        "--tb=short"
    ]
    
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    # Check if we should use LocalStack
    if "--localstack" in sys.argv:
        os.environ["USE_LOCALSTACK"] = "true"
        if not ensure_localstack_running():
            print("Please start LocalStack first!")
            sys.exit(1)
    
    exit_code = run_infrastructure_tests()
    sys.exit(exit_code)
"""
Utility functions for running tests
"""
import os
import sys
import subprocess
import time
from pathlib import Path


def run_infrastructure_tests():
    """Run infrastructure tests with proper environment setup"""
    # Set test environment variables
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    # Change to backend directory
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)

    # Run pytest
    cmd = [sys.executable, "-m", "pytest", "tests/infrastructure/", "-v", "--tb=short"]

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    exit_code = run_infrastructure_tests()
    sys.exit(exit_code)

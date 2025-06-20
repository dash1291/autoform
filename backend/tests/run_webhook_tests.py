#!/usr/bin/env python3
"""
Script to run webhook credential selection tests
"""
import sys
import subprocess
import os

def run_tests():
    """Run the webhook credential tests"""
    
    # Add the backend directory to Python path
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, backend_dir)
    
    # Set environment variables for testing
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
    
    # Run the specific webhook tests
    test_file = os.path.join(os.path.dirname(__file__), "test_webhook_credentials.py")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            test_file,
            "-v",  # verbose output
            "--tb=short",  # shorter traceback format
            "--disable-warnings"  # suppress warnings for cleaner output
        ], cwd=backend_dir, check=True)
        
        print("✅ All webhook credential tests passed!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Tests failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print("❌ pytest not found. Please install pytest:")
        print("   pip install pytest pytest-asyncio")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
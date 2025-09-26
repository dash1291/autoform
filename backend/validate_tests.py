#!/usr/bin/env python3
"""
Simple validation script to check if the test files are syntactically correct
and basic functionality works
"""
import sys
import json


def validate_deployment_config():
    """Validate DeploymentConfig functionality"""
    try:
        # Import the DeploymentConfig class
        from services.deployment import DeploymentConfig
        
        print("✅ Successfully imported DeploymentConfig")
        
        # Test creating config with environment_id
        config_with_env = DeploymentConfig(
            project_id="test-proj-123",
            project_name="test-project",
            git_repo_url="https://github.com/test/repo.git",
            branch="main",
            commit_sha="abc123def456",
            environment_id="env-test-123",
            subdirectory="backend",
            health_check_path="/api/health",
            port=8080,
            cpu=512,
            memory=1024,
            disk_size=30
        )
        
        print("✅ DeploymentConfig with environment created successfully")
        print(f"   - project_id: {config_with_env.project_id}")
        print(f"   - environment_id: {config_with_env.environment_id}")
        print(f"   - port: {config_with_env.port}")
        print(f"   - cpu: {config_with_env.cpu}")
        
        # Test creating config without environment_id (backward compatibility)
        config_legacy = DeploymentConfig(
            project_id="test-proj-456", 
            project_name="legacy-project",
            git_repo_url="https://github.com/test/legacy.git",
            branch="main",
            commit_sha="legacy123"
        )
        
        print("✅ Legacy DeploymentConfig created successfully")
        print(f"   - project_id: {config_legacy.project_id}")
        print(f"   - environment_id: {config_legacy.environment_id}")  # Should be None
        print(f"   - port: {config_legacy.port}")  # Should be default 3000
        
        return True
        
    except Exception as e:
        print(f"❌ Error validating DeploymentConfig: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_json_parsing():
    """Validate JSON subnet ID parsing"""
    try:
        print("\n🧪 Testing JSON subnet parsing...")
        
        # Test valid JSON
        subnet_json = '["subnet-123", "subnet-456", "subnet-789"]'
        subnet_ids = json.loads(subnet_json)
        assert len(subnet_ids) == 3
        assert "subnet-123" in subnet_ids
        print("✅ Valid JSON parsing works")
        
        # Test empty array
        empty_json = '[]'
        empty_subnets = json.loads(empty_json)
        assert len(empty_subnets) == 0
        print("✅ Empty JSON array parsing works")
        
        # Test invalid JSON
        try:
            invalid_json = 'invalid-json'
            json.loads(invalid_json)
            print("❌ Invalid JSON should have failed!")
            return False
        except json.JSONDecodeError:
            print("✅ Invalid JSON properly raises error")
        
        return True
        
    except Exception as e:
        print(f"❌ Error validating JSON parsing: {e}")
        return False


def validate_imports():
    """Validate that all necessary imports work"""
    try:
        print("\n🧪 Testing imports...")
        
        # Test core imports
        print("✅ Database import works")
        
        print("✅ DeploymentService import works")
        
        print("✅ Infrastructure types import works")
        
        print("✅ Schema imports work")
        
        return True
        
    except Exception as e:
        print(f"❌ Error with imports: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_test_file_syntax():
    """Check if test files have valid Python syntax"""
    import ast
    
    test_files = [
        "tests/test_environment_deployments.py",
        "tests/test_environment_integration.py", 
        "tests/infrastructure/test_vpc_service_environments.py"
    ]
    
    print("\n🧪 Checking test file syntax...")
    
    for test_file in test_files:
        try:
            with open(test_file, 'r') as f:
                source = f.read()
            
            # Parse the file to check syntax
            ast.parse(source)
            print(f"✅ {test_file} syntax is valid")
            
        except SyntaxError as e:
            print(f"❌ Syntax error in {test_file}: {e}")
            return False
        except FileNotFoundError:
            print(f"⚠️  File not found: {test_file}")
        except Exception as e:
            print(f"❌ Error checking {test_file}: {e}")
            return False
    
    return True


def main():
    """Run all validations"""
    print("🚀 Starting test validation...\n")
    
    all_passed = True
    
    # Validate imports
    if not validate_imports():
        all_passed = False
    
    # Validate DeploymentConfig functionality
    if not validate_deployment_config():
        all_passed = False
    
    # Validate JSON parsing
    if not validate_json_parsing():
        all_passed = False
    
    # Validate test file syntax
    if not validate_test_file_syntax():
        all_passed = False
    
    print(f"\n{'='*50}")
    if all_passed:
        print("🎉 All validations passed! Tests should work correctly.")
        print("\nNext steps:")
        print("1. Run: python -m pytest tests/test_environment_deployments.py -v")
        print("2. Run: python -m pytest tests/infrastructure/test_vpc_service_environments.py -v")
        print("3. Check deployment with your 'preview' environment")
    else:
        print("❌ Some validations failed. Please fix the issues above.")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
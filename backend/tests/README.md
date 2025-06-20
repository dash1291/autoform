# Autoform Backend Integration Tests

This directory contains integration tests for the Autoform backend infrastructure services.

## Test Structure

```
tests/
├── infrastructure/          # Infrastructure service tests
│   ├── test_working_services.py    # Comprehensive infrastructure service tests
│   └── test_simple_vpc.py          # Simple VPC service tests
├── test_webhook_credentials.py     # Webhook auto-deployment credential tests
├── run_webhook_tests.py           # Script to run webhook tests
├── conftest.py             # Shared pytest fixtures
└── test_utils.py          # Test utility functions
```

## Running Tests

### Prerequisites

1. Install development dependencies:
```bash
cd backend
rye sync
```

### Using Moto (Default - No Docker Required)

The tests use [moto](https://github.com/spulec/moto) by default, which mocks AWS services in-memory:

```bash
# Run all infrastructure tests
python -m pytest tests/infrastructure/ -v

# Run working infrastructure tests (recommended)
python -m pytest tests/infrastructure/test_working_services.py -v

# Run simple VPC tests
python -m pytest tests/infrastructure/test_simple_vpc.py -v

# Run specific test
python -m pytest tests/infrastructure/test_working_services.py::TestWorkingVPCService::test_vpc_service_initialization -v

# Run webhook credential tests
python -m pytest tests/test_webhook_credentials.py -v

# Or use the dedicated script
python tests/run_webhook_tests.py
```

### Using LocalStack (Optional - Requires Docker)

For more realistic testing with LocalStack:

1. Start LocalStack:
```bash
docker-compose up -d localstack
```

2. Run tests with LocalStack:
```bash
USE_LOCALSTACK=true python -m pytest tests/infrastructure/ -v
```

3. Or use the test utility:
```bash
python tests/test_utils.py --localstack
```

## Test Coverage

### Working Infrastructure Tests (`test_working_services.py`)
**VPC Service Tests:**
- ✅ VPC infrastructure initialization
- ✅ VPC creation with CIDR blocks
- ✅ Subnet creation and configuration
- ✅ Security group creation
- ✅ Existing VPC/subnet handling

**ECS Service Tests:**
- ✅ ECS cluster creation and management
- ✅ Task definition creation with environment variables
- ✅ Container configuration (CPU, memory, ports)
- ✅ Fargate task definition setup

**IAM Service Tests:**
- ✅ ECS execution role creation
- ✅ ECS task role with proper permissions
- ✅ CodeBuild role for CI/CD builds
- ✅ Role ARN verification

**Service Integration Tests:**
- ✅ VPC-to-ECS resource sharing
- ✅ IAM-to-ECS role assignment
- ✅ Cross-service resource validation

### Webhook Credential Tests (`test_webhook_credentials.py`)
**Auto-Deployment Credential Selection:**
- ✅ Team projects use team AWS credentials
- ✅ Personal projects use user AWS credentials  
- ✅ Credential decryption and validation
- ✅ Missing credentials handled gracefully
- ✅ Invalid credentials handled gracefully
- ✅ Project not found handled gracefully
- ✅ DeploymentService receives correct configuration

## Writing New Tests

When adding new infrastructure tests:

1. Create test file in `tests/infrastructure/`
2. Use the provided fixtures from `conftest.py`
3. Follow the naming convention: `test_<service_name>.py`
4. Use async test functions with `pytest_asyncio`
5. Mock AWS services using the `mock_aws_services` fixture

Example test structure:

```python
import pytest
import pytest_asyncio
from infrastructure.services.new_service import NewService

class TestNewService:
    @pytest_asyncio.fixture
    async def service(self, test_project_config, test_region, aws_credentials, mock_aws_services):
        service = NewService(
            project_name=test_project_config["project_name"],
            region=test_region,
            aws_credentials=aws_credentials
        )
        yield service
    
    async def test_functionality(self, service):
        # Test implementation
        result = await service.some_method()
        assert result is not None
```

## Debugging Tests

For verbose output:
```bash
pytest -vv -s tests/infrastructure/
```

For specific test with full traceback:
```bash
pytest tests/infrastructure/test_vpc_service.py::TestVPCService::test_create_vpc -vv --tb=long
```

## CI/CD Integration

These tests should be run in CI/CD pipelines before deployment:

```yaml
# Example GitHub Actions
- name: Run Infrastructure Tests
  run: |
    cd backend
    python -m pytest tests/infrastructure/ --tb=short
- name: Run Webhook Credential Tests
  run: |
    cd backend
    python -m pytest tests/test_webhook_credentials.py --tb=short
```
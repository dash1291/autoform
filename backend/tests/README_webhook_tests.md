# Webhook Tests Documentation

This directory contains comprehensive tests for the shared webhook functionality implemented in the autoform backend.

## Test Files

### `test_projects_webhook.py`
Tests for the `/projects/{project_id}/webhook/` endpoints that manage webhook configuration.

**Test Coverage:**
- `TestProjectWebhookConfigure`: Tests webhook configuration endpoint
  - Creating new webhooks for repositories
  - Reusing existing webhooks for same repository
  - Handling project not found errors
  - GitHub API failure scenarios
  
- `TestProjectWebhookDelete`: Tests webhook deletion endpoint
  - Removing project associations
  - Preserving shared webhooks when other projects use them
  - GitHub webhook deletion with tokens
  - Project not found handling

- `TestSharedWebhookScenarios`: Tests shared webhook behavior
  - Multiple projects sharing webhooks for same repository
  - Different repositories getting separate webhooks

### `test_webhook_integration.py`
Integration tests for the webhook processing functionality that handles incoming GitHub webhooks.

**Test Coverage:**
- `TestWebhookIntegration`: Tests webhook processing with shared webhooks
  - Processing multiple projects with shared webhooks
  - Signature verification with shared secrets
  - Invalid signature rejection
  - Missing webhook configuration handling
  - Branch filtering
  - Inactive webhook handling
  - Subdirectory-based filtering

## Key Features Tested

### Shared Webhook Functionality
- **Single Webhook per Repository**: Multiple projects from the same GitHub repository share a single webhook configuration
- **Signature Verification**: All projects use the same shared secret for webhook signature verification
- **Automatic Cleanup**: Webhooks are automatically deleted when no projects reference them

### Project Isolation
- **Branch Filtering**: Only projects matching the push branch are processed
- **Subdirectory Filtering**: Projects with subdirectories only deploy when files in their subdirectory change
- **Auto-deploy Settings**: Only projects with auto-deploy enabled are processed

### Error Handling
- **Missing Projects**: Graceful handling of project not found scenarios
- **Invalid Signatures**: Proper rejection of webhooks with invalid signatures
- **GitHub API Failures**: Fallback to manual instructions when GitHub API fails
- **Inactive Webhooks**: Proper handling of deactivated webhooks

## Running Tests

Run all webhook tests:
```bash
rye run pytest tests/test_projects_webhook.py tests/test_webhook_integration.py -v
```

Run specific test categories:
```bash
# Project endpoint tests only
rye run pytest tests/test_projects_webhook.py -v

# Integration tests only
rye run pytest tests/test_webhook_integration.py -v
```

## Test Architecture

The tests use:
- **AsyncMock**: For mocking async database operations
- **MagicMock**: For mocking synchronous dependencies
- **pytest fixtures**: For reusable test data and mocks
- **unittest.mock.patch**: For dependency injection during tests

## Mock Objects

- `MockUser`: Simulates user authentication
- `MockProject`: Represents project database records
- `MockWebhook`: Represents webhook database records
- `MockGitHubWebhookService`: Mocks GitHub API interactions

## Coverage

These tests provide comprehensive coverage of:
1. ✅ Webhook configuration workflows
2. ✅ Shared webhook creation and management
3. ✅ Webhook processing and filtering logic
4. ✅ Error scenarios and edge cases
5. ✅ GitHub integration points
6. ✅ Database relationship management

The tests ensure that the shared webhook system works correctly and maintains backward compatibility while providing the new shared functionality.
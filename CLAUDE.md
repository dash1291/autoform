# Claude AI Context File

## Guidelines
- Do not use emojis in generated code and docs unless specifically asked

## Debugging Lessons Learned

**Variable shadowing and misleading logs**: When debugging AWS region issues, don't trust log statements alone - verify actual API behavior by checking what resources are returned, as local variable overrides can cause clients to use different regions than what logs indicate.

## Credential Management Anti-Patterns

**Hidden fallback logic causes security confusion**: Always audit credential selection logic for unintended fallbacks. Found multiple places where "team credentials → personal credentials → default" fallback was causing users to unknowingly access resources with wrong credential context. 

**Key fixes applied**:
- Eliminated fallback logic in `get_team_aws_credentials()` functions
- Made credential selection explicit and context-aware (team projects = team creds only, personal projects = personal creds only)
- Added parameter-based credential type selection for API endpoints
- Updated frontend to specify credential context explicitly

**Security principle**: Credential selection should be explicit, not implicit. Users should always know exactly which credentials are being used for their operations.

## Infrastructure Development Practices

**Test-Driven Infrastructure Changes**: When using moto for infrastructure testing, always write tests before making code changes. After implementing modifications, run tests to ensure both new and existing scenarios pass successfully.
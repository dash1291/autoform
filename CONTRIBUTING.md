# Contributing to AutoForm

Thanks for your interest in contributing. Please read this guide before opening a pull request.

## Getting Started

Follow the [installation steps in the README](README.md#installation) to set up your local development environment.

## Development Workflow

1. Fork the repository and create a branch from `main`
2. Make your changes
3. Ensure linting and tests pass (see below)
4. Open a pull request — please link any related issue

## Code Style

### Backend (Python)

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
cd backend

# Check for lint errors
rye run ruff check .

# Auto-fix where possible
rye run ruff check . --fix
```

### Frontend (TypeScript)

```bash
cd frontend

# Lint
npm run lint

# Type check
npm run typecheck
```

## Running Tests

Backend tests use [moto](https://docs.getmoto.org/) to mock AWS services — no real AWS account is needed.

```bash
cd backend
rye run pytest tests/infrastructure/
```

## Opening Issues

- Search existing issues before opening a new one
- For bugs, include steps to reproduce, expected behavior, and actual behavior
- For features, describe the use case and why it belongs in the project

## Pull Requests

- Keep PRs focused — one concern per PR
- Include a clear description of what changed and why
- Link the related issue if one exists
- PRs require passing CI before merge

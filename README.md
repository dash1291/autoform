# AutoForm - AWS ECS Deployment Platform

A platform for easily deploying applications to AWS ECS with automatic infrastructure provisioning.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **GitHub Integration**: Authenticate with GitHub and deploy directly from repositories
- **Team Collaboration**: Create teams, manage members, and share projects
- **Team AWS Configuration**: Each team can configure their own AWS credentials for deployments
- **Automatic Infrastructure**: Automatically provisions AWS resources (VPC, ECS, ALB)
- **Environment Variables**: Secure management with AWS Secrets Manager
- **Real-time Logs**: Stream deployment logs in real-time
- **Resource Configuration**: Configure CPU, memory, and disk for each project
- **Branch Selection**: Deploy from any branch with automatic branch detection
- **Health Checks**: Configurable health check endpoints
- **Subdirectory Support**: Deploy from monorepo subdirectories
- **Secure Credential Storage**: Team AWS credentials are encrypted before storage

## Getting Started

### Prerequisites
- Node.js 18+
- Python 3.11+ with [rye](https://rye.astral.sh/)
- PostgreSQL
- Redis (for background tasks)
- AWS Account with appropriate permissions

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/autoform.git
cd autoform
```

2. Install frontend dependencies:
```bash
cd frontend && npm install
```

3. Install backend dependencies:
```bash
cd backend && rye sync
```

4. Set up environment variables:
```bash
cp frontend/.env.example frontend/.env
cp backend/.env.example backend/.env
```

5. Generate an encryption key and set it as `ENCRYPTION_KEY` in `backend/.env`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

6. Set up the database:
```bash
cd backend
rye run prisma generate
rye run alembic upgrade head
```

### Development

Run both frontend and backend:
```bash
npm run dev
```

Or separately:
```bash
npm run dev:frontend   # http://localhost:3000
npm run dev:backend    # http://localhost:8000
```

## Tech Stack

### Frontend
- **Framework**: Next.js 14 with App Router
- **UI**: React with TypeScript
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui
- **Authentication**: JWT with GitHub OAuth

### Backend
- **Framework**: FastAPI (Python)
- **Package Manager**: rye
- **Database**: PostgreSQL with SQLModel
- **Migrations**: Alembic
- **Authentication**: JWT with GitHub OAuth
- **AWS SDK**: boto3
- **Background Tasks**: Celery with Redis
- **Infrastructure**:
  - ECS for container orchestration
  - ALB for load balancing
  - ECR for container registry
  - CodeBuild for building Docker images

## Contributing

Contributions are welcome. Please open an issue to discuss your proposed change before submitting a pull request.

## License

MIT

# AutoForm - AWS ECS Deployment Platform

A platform for easily deploying applications to AWS ECS with automatic infrastructure provisioning.

## Project Structure

```
autoform/
├── frontend/              # Next.js frontend application
│   ├── src/              # Frontend source code
│   │   ├── app/          # Next.js app directory
│   │   ├── components/   # React components
│   │   ├── lib/          # Utility functions
│   │   └── types/        # TypeScript types
│   ├── public/           # Static assets
│   ├── package.json      # Frontend dependencies
│   └── next.config.js    # Next.js configuration
│
├── backend/              # FastAPI backend application
│   ├── app/              # Application code
│   │   └── routers/      # API endpoints
│   ├── core/             # Core utilities (config, database, security)
│   ├── infrastructure/   # AWS infrastructure code (boto3)
│   ├── schemas/          # Pydantic models
│   ├── services/         # Business logic services
│   ├── main.py           # FastAPI application entry point
│   └── requirements.txt  # Python dependencies
│
├── prisma/               # Database schema (shared)
│   └── schema.prisma     # Prisma schema definition
│
├── infrastructure/       # Legacy TypeScript infrastructure (to be removed)
└── package.json          # Root package.json for running both frontend and backend
```

## Tech Stack

### Frontend
- **Framework**: Next.js 14 with App Router
- **UI**: React with TypeScript
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui
- **Authentication**: NextAuth.js (migrating to JWT)
- **State Management**: React hooks

### Backend
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL with Prisma ORM
- **Authentication**: JWT with GitHub OAuth
- **AWS SDK**: boto3
- **Background Tasks**: Celery with Redis
- **Infrastructure**: 
  - ECS for container orchestration
  - ALB for load balancing
  - ECR for container registry
  - CodeBuild for building Docker images

## Getting Started

### Prerequisites
- Node.js 18+
- Python 3.11+
- PostgreSQL
- Redis (for background tasks)
- AWS Account with appropriate permissions

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/autoform.git
cd autoform
```

2. Install dependencies:
```bash
# Install all dependencies (frontend + backend)
npm run install:all
```

3. Set up environment variables:
```bash
# Frontend
cp frontend/.env.example frontend/.env

# Backend
cp backend/.env.example backend/.env
```

4. Generate encryption key for team AWS credentials:
```bash
# Generate a new encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Copy the output and replace the ENCRYPTION_KEY value in backend/.env
```

Alternative methods to generate encryption key:
```bash
# Using OpenSSL
openssl rand -base64 32

# Using Python secrets module
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

5. Set up the database:
```bash
# Generate Prisma client
npm run prisma:generate

# Run migrations
npm run prisma:migrate
```

### Development

Run both frontend and backend in development mode:
```bash
npm run dev
```

Or run them separately:
```bash
# Frontend only (runs on http://localhost:3000)
npm run dev:frontend

# Backend only (runs on http://localhost:8000)
npm run dev:backend
```

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

## Security

### Team AWS Credentials
- Team AWS credentials are encrypted using Fernet (AES 128-bit) before storage
- Encryption key should be generated using cryptographically secure methods
- Only team owners can configure AWS credentials
- Credentials are never returned in API responses (only masked versions)

### Important Security Notes
- **Never commit `.env` files to version control**
- **Use different encryption keys for different environments**
- **Store production encryption keys securely** (e.g., AWS Secrets Manager)
- **Rotate encryption keys periodically** (requires re-encrypting existing data)

## API Documentation

When running the backend, API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT
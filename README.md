# Autoform

A Heroku-like Platform-as-a-Service (PaaS) system that deploys applications to AWS ECS.

## Features

- GitHub OAuth authentication
- Automatic Docker image building and pushing to ECR
- One-click deployment to AWS ECS with Fargate
- Deployment logs and runtime logs from one place

## Getting Started

### Prerequisites

- Node.js 18+
- Docker
- AWS CLI configured with appropriate permissions
- GitHub OAuth App

### Setup

1. Clone and install:
```bash
git clone <your-repo-url>
cd autoform
npm install
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Set up the database:

**For local PostgreSQL:**
```bash
# Start local database
npm run db:up

# Run migrations
npm run db:migrate
```

4. Start development server:
```bash
npm run dev
```

### Required Environment Variables

- `DATABASE_URL` - PostgreSQL connection string
- `NEXTAUTH_SECRET` - Random secret for NextAuth.js
- `GITHUB_ID` & `GITHUB_SECRET` - GitHub OAuth app credentials
- `AWS_REGION` - AWS region (default: us-east-1)
- AWS credentials via AWS CLI or environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

### GitHub OAuth Setup

Create a GitHub OAuth App:
- Homepage URL: `http://localhost:3000`
- Callback URL: `http://localhost:3000/api/auth/callback/github`
- Required scopes: `read:user`, `user:email`, `repo`

## Usage

1. **Sign in** with your GitHub account
2. **Create a project** by providing:
   - Project name
   - GitHub repository URL (must contain a Dockerfile)
3. **Deploy** your application:
   - System clones your repository
   - Builds Docker image for linux/amd64
   - Pushes to ECR
   - Provisions AWS infrastructure (VPC, ECS, ALB)
   - Deploys to ECS Fargate

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run typecheck` - Run TypeScript checks
- `npm run db:up` - Start PostgreSQL with Docker
- `npm run db:migrate` - Run database migrations

### Docker Scripts

- `npm run docker:build` - Build Docker image
- `npm run docker:run` - Run Docker container
- `npm run docker:dev` - Build and run Docker container

## Docker Deployment

### Building the Docker Image

```bash
# Build the Docker image
npm run docker:build

# Or use Docker directly
docker build -t autoform .
```

### Running with Docker

```bash
# Run with environment file
npm run docker:run

# Or run with Docker directly
docker run -p 3000:3000 --env-file .env autoform

# Run with individual environment variables
docker run -p 3000:3000 \\
  -e DATABASE_URL="your-database-url" \\
  -e NEXTAUTH_SECRET="your-secret" \\
  -e GITHUB_ID="your-github-id" \\
  -e GITHUB_SECRET="your-github-secret" \\
  autoform
```

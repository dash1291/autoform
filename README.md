# Autoform

A Heroku-like Platform-as-a-Service (PaaS) system that deploys applications to AWS ECS.

## Features

- 🔐 GitHub OAuth authentication
- 📦 Automatic Docker image building and pushing to ECR
- 🚀 One-click deployment to AWS ECS with Fargate
- 🏗️ Automatic AWS infrastructure provisioning (VPC, ECS, ALB)
- 📊 Real-time deployment logs and status tracking
- ⚡ Project management with deployment history
- 🛑 Deployment abort functionality

## Tech Stack

- **Frontend**: Next.js 14 with TypeScript and Tailwind CSS
- **Authentication**: NextAuth.js with GitHub provider
- **Database**: PostgreSQL with Prisma ORM
- **Infrastructure**: AWS SDK (ECS, ECR, VPC, ALB, IAM)
- **Container Registry**: Amazon ECR
- **Orchestration**: Amazon ECS with Fargate
- **Load Balancing**: Application Load Balancer (ALB)

## Getting Started

### Prerequisites

- Node.js 18+
- Docker
- AWS CLI configured with appropriate permissions
- GitHub OAuth App

### Setup

1. Clone and install:
\`\`\`bash
git clone <your-repo-url>
cd autoform
npm install
\`\`\`

2. Configure environment:
\`\`\`bash
cp .env.example .env
# Edit .env with your credentials
\`\`\`

3. Start database and run migrations:
\`\`\`bash
npm run db:up
npm run db:migrate
\`\`\`

4. Start development server:
\`\`\`bash
npm run dev
\`\`\`

### Required Environment Variables

- \`DATABASE_URL\` - PostgreSQL connection string
- \`NEXTAUTH_SECRET\` - Random secret for NextAuth.js
- \`GITHUB_ID\` & \`GITHUB_SECRET\` - GitHub OAuth app credentials
- \`AWS_REGION\` - AWS region (default: us-east-1)
- AWS credentials via AWS CLI or environment variables

### GitHub OAuth Setup

Create a GitHub OAuth App:
- Homepage URL: \`http://localhost:3000\`
- Callback URL: \`http://localhost:3000/api/auth/callback/github\`
- Required scopes: \`read:user\`, \`user:email\`, \`repo\`

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

## Project Structure

\`\`\`
src/
├── app/                 # Next.js app router
│   ├── api/            # API routes for projects, deployments
│   ├── dashboard/      # Dashboard page
│   └── projects/       # Project management pages
├── components/          # React components
├── lib/                # Core services (auth, deployment, database)
└── types/              # TypeScript definitions
infrastructure/         # AWS infrastructure provisioning
prisma/                # Database schema
\`\`\`

## Available Scripts

- \`npm run dev\` - Start development server
- \`npm run build\` - Build for production
- \`npm run typecheck\` - Run TypeScript checks
- \`npm run db:up\` - Start PostgreSQL with Docker
- \`npm run db:migrate\` - Run database migrations
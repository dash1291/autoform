# Autopilot PaaS

A Heroku-like Platform-as-a-Service (PaaS) system that deploys applications to AWS ECS.

## Features

- 🔐 GitHub OAuth authentication
- 📦 Automatic Docker image building and pushing to ECR
- 🚀 One-click deployment to AWS ECS with Fargate
- 🔧 Infrastructure provisioning with Pulumi
- 📊 Real-time deployment status tracking
- 🌐 Automatic load balancer setup

## Tech Stack

- **Frontend**: Next.js 14 with TypeScript
- **Authentication**: NextAuth.js with GitHub provider
- **Database**: PostgreSQL with Prisma ORM
- **Infrastructure**: Pulumi with AWS provider
- **Container Registry**: Amazon ECR
- **Orchestration**: Amazon ECS with Fargate
- **Load Balancing**: Application Load Balancer (ALB)

## Getting Started

### Prerequisites

- Node.js 18+
- Docker
- AWS CLI configured
- PostgreSQL database
- GitHub OAuth App

### Installation

1. Clone the repository:
\`\`\`bash
git clone <your-repo-url>
cd autopilot
\`\`\`

2. Install dependencies:
\`\`\`bash
npm install
\`\`\`

3. Set up environment variables:
\`\`\`bash
cp .env.example .env
\`\`\`

4. Configure your `.env` file with:
   - Database connection string
   - GitHub OAuth credentials
   - AWS credentials
   - Pulumi access token

5. Set up the database:
\`\`\`bash
npx prisma migrate dev
\`\`\`

6. Start the development server:
\`\`\`bash
npm run dev
\`\`\`

### AWS Setup

1. Create an ECR repository for your projects
2. Ensure your AWS credentials have the necessary permissions:
   - ECS full access
   - ECR full access
   - VPC full access
   - IAM role creation
   - CloudWatch logs

### GitHub OAuth Setup

1. Go to GitHub Settings > Developer settings > OAuth Apps
2. Create a new OAuth App with:
   - Homepage URL: \`http://localhost:3000\`
   - Authorization callback URL: \`http://localhost:3000/api/auth/callback/github\`

## Usage

1. **Sign in** with your GitHub account
2. **Create a project** by providing:
   - Project name
   - Git repository URL
3. **Deploy** your application:
   - The system will clone your repo
   - Build a Docker image
   - Push to ECR
   - Deploy to ECS with auto-scaling

## Project Structure

\`\`\`
src/
├── app/                 # Next.js app router pages
├── components/          # React components
├── lib/                 # Utility libraries
├── types/               # TypeScript type definitions
infrastructure/          # Pulumi infrastructure code
prisma/                  # Database schema and migrations
\`\`\`

## Deployment Flow

1. **Repository Clone**: Git repository is cloned to a temporary directory
2. **Image Build**: Docker image is built from the repository
3. **ECR Push**: Image is tagged and pushed to Amazon ECR
4. **Infrastructure**: Pulumi provisions ECS cluster, service, and ALB
5. **Service Deploy**: ECS service is updated with the new image

## Contributing

1. Fork the repository
2. Create your feature branch (\`git checkout -b feature/amazing-feature\`)
3. Commit your changes (\`git commit -m 'Add some amazing feature'\`)
4. Push to the branch (\`git push origin feature/amazing-feature\`)
5. Open a Pull Request

## License

This project is licensed under the MIT License.
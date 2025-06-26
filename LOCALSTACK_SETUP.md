# LocalStack Setup for Local AWS Testing

This guide explains how to set up LocalStack for local AWS service emulation during development.

## Prerequisites

- Docker and Docker Compose installed
- AWS CLI with LocalStack wrapper (`awslocal`)

## Installation

1. Install AWS CLI LocalStack wrapper:
   ```bash
   pip install awscli-local
   ```

2. Configure environment variables in your `.env` file:
   ```bash
   USE_LOCALSTACK=true
   LOCALSTACK_HOST=localhost
   LOCALSTACK_PORT=4566
   ```

## Running LocalStack

1. Start LocalStack services:
   ```bash
   docker-compose -f docker-compose.localstack.yml up -d
   ```

2. Initialize AWS resources (run after LocalStack is up):
   ```bash
   chmod +x localstack-init/init-aws.sh
   ./localstack-init/init-aws.sh
   ```

## Verification

Check that LocalStack is running and initialized:
```bash
awslocal sts get-caller-identity
awslocal ec2 describe-vpcs
awslocal ecs list-clusters
```

## Usage

When `USE_LOCALSTACK=true` is set, all AWS client calls will automatically route to LocalStack instead of real AWS services. This allows you to:

- Test ECS deployments locally
- Test S3 operations
- Test ECR operations
- Test all other AWS services without incurring costs

## Services Available

LocalStack provides the following AWS services:
- S3 (Simple Storage Service)
- ECS (Elastic Container Service)
- ECR (Elastic Container Registry)
- Secrets Manager
- IAM (Identity and Access Management)
- STS (Security Token Service)
- ELBv2 (Application Load Balancer)
- EC2 (Virtual Private Cloud, Subnets)
- CloudWatch Logs
- CodeBuild

## Cleanup

To stop and remove LocalStack:
```bash
docker-compose -f docker-compose.localstack.yml down
docker volume rm autoform_localstack_data
```
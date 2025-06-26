#!/bin/bash

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
awslocal sts get-caller-identity

# Create default VPC and subnets
echo "Creating default VPC..."
VPC_ID=$(awslocal ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text)
awslocal ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=localstack-default-vpc

# Create subnets
echo "Creating subnets..."
SUBNET1_ID=$(awslocal ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 --availability-zone us-east-1a --query 'Subnet.SubnetId' --output text)
SUBNET2_ID=$(awslocal ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.2.0/24 --availability-zone us-east-1b --query 'Subnet.SubnetId' --output text)

awslocal ec2 create-tags --resources $SUBNET1_ID --tags Key=Name,Value=localstack-subnet-1
awslocal ec2 create-tags --resources $SUBNET2_ID --tags Key=Name,Value=localstack-subnet-2

# Create ECS cluster
echo "Creating ECS cluster..."
awslocal ecs create-cluster --cluster-name localstack-default-cluster

# Create ECR repository for testing
echo "Creating ECR repository..."
awslocal ecr create-repository --repository-name autoform-test || true

# Create S3 buckets for deployments
echo "Creating S3 buckets..."
awslocal s3 mb s3://autoform-deployments-localstack || true
awslocal s3 mb s3://autoform-codebuild-localstack || true

# Create IAM roles for ECS
echo "Creating IAM roles..."
awslocal iam create-role --role-name ecsTaskExecutionRole --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}' || true

awslocal iam attach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy || true

echo "LocalStack initialization complete!"
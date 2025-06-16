#!/bin/bash

# Script to create Docker Hub credentials in AWS Secrets Manager for CodeBuild
# This helps avoid Docker Hub rate limiting during builds

echo "Setting up Docker Hub credentials for CodeBuild..."

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "❌ AWS CLI is not configured or you don't have permissions"
    echo "Please run 'aws configure' first"
    exit 1
fi

# Get AWS region (default to us-east-1 if not set)
AWS_REGION=${AWS_REGION:-$(aws configure get region)}
AWS_REGION=${AWS_REGION:-us-east-1}

echo "Using AWS region: $AWS_REGION"

# Prompt for Docker Hub credentials
echo ""
echo "Please provide your Docker Hub credentials:"
echo "Note: Use an access token instead of your password for better security"
echo "You can create an access token at: https://hub.docker.com/settings/security"
echo ""

read -p "Docker Hub Username: " DOCKERHUB_USERNAME
read -s -p "Docker Hub Password/Token: " DOCKERHUB_PASSWORD
echo ""

if [ -z "$DOCKERHUB_USERNAME" ] || [ -z "$DOCKERHUB_PASSWORD" ]; then
    echo "❌ Username and password/token are required"
    exit 1
fi

# Create the secret JSON
SECRET_VALUE=$(cat <<EOF
{
  "username": "$DOCKERHUB_USERNAME",
  "password": "$DOCKERHUB_PASSWORD"
}
EOF
)

# Create or update the secret
SECRET_NAME="dockerhub-credentials"

echo "Creating/updating secret: $SECRET_NAME"

# Check if secret already exists
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "Secret already exists, updating..."
    aws secretsmanager update-secret \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --region "$AWS_REGION"
    
    if [ $? -eq 0 ]; then
        echo "✅ Successfully updated Docker Hub credentials secret"
    else
        echo "❌ Failed to update secret"
        exit 1
    fi
else
    echo "Creating new secret..."
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "Docker Hub credentials for CodeBuild to avoid rate limiting" \
        --secret-string "$SECRET_VALUE" \
        --region "$AWS_REGION"
    
    if [ $? -eq 0 ]; then
        echo "✅ Successfully created Docker Hub credentials secret"
    else
        echo "❌ Failed to create secret"
        exit 1
    fi
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "The secret '$SECRET_NAME' has been created in AWS Secrets Manager."
echo "CodeBuild will now automatically use these credentials when available."
echo ""
echo "Important notes:"
echo "- Use Docker Hub access tokens instead of passwords for better security"
echo "- You can create access tokens at: https://hub.docker.com/settings/security"
echo "- The secret is region-specific (created in: $AWS_REGION)"
echo ""

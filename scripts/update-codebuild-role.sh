#!/bin/bash

# Script to add Secrets Manager permissions to CodeBuild service role
# This allows CodeBuild to access Docker Hub credentials

echo "Updating CodeBuild service role with Secrets Manager permissions..."

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "❌ AWS CLI is not configured or you don't have permissions"
    echo "Please run 'aws configure' first"
    exit 1
fi

# Get AWS region and account ID
AWS_REGION=${AWS_REGION:-$(aws configure get region)}
AWS_REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Using AWS region: $AWS_REGION"
echo "Account ID: $ACCOUNT_ID"

ROLE_NAME="CodeBuildServiceRole"
POLICY_NAME="SecretsManagerDockerHubAccess"

# Create the policy document
POLICY_DOCUMENT=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": [
                "arn:aws:secretsmanager:${AWS_REGION}:${ACCOUNT_ID}:secret:dockerhub-credentials*"
            ]
        }
    ]
}
EOF
)

echo "Policy document:"
echo "$POLICY_DOCUMENT"
echo ""

# Check if the role exists
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    echo "❌ CodeBuild service role '$ROLE_NAME' not found"
    echo "The role will be created automatically when you run your first deployment"
    echo "Please run a deployment first, then run this script again"
    exit 1
fi

echo "✅ CodeBuild service role found: $ROLE_NAME"

# Check if policy is already attached
if aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" >/dev/null 2>&1; then
    echo "Policy already exists, updating..."
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "$POLICY_NAME" \
        --policy-document "$POLICY_DOCUMENT"
else
    echo "Creating new policy..."
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "$POLICY_NAME" \
        --policy-document "$POLICY_DOCUMENT"
fi

if [ $? -eq 0 ]; then
    echo "✅ Successfully added Secrets Manager permissions to CodeBuild role"
    echo ""
    echo "🎉 Setup complete!"
    echo ""
    echo "CodeBuild can now access the dockerhub-credentials secret."
    echo "Your next deployment should authenticate with Docker Hub automatically."
else
    echo "❌ Failed to add permissions to CodeBuild role"
    exit 1
fi
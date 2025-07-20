#!/bin/bash

echo "Setting up CodeBuildServiceRole..."

# Create permissions policy document
cat > permissions-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:GetAuthorizationToken",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetBucketLocation",
        "s3:ListBucket"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:GetLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Resource": "*"
    }
  ]
}
EOF

export AWS_PROFILE=personal

# Check if role exists
if aws iam get-role --role-name CodeBuildServiceRole >/dev/null 2>&1; then
    echo "Role already exists, updating permissions..."
    
    # Update the permissions policy
    aws iam put-role-policy \
      --role-name CodeBuildServiceRole \
      --policy-name CodeBuildServicePolicy \
      --policy-document file://permissions-policy.json
    
    echo "✅ CodeBuildServiceRole permissions updated successfully!"
else
    echo "Role doesn't exist, creating new role..."
    
    # Create trust policy document
    cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create the IAM role
    aws iam create-role \
      --role-name CodeBuildServiceRole \
      --assume-role-policy-document file://trust-policy.json \
      --description "Service role for CodeBuild to build Docker images"

    # Attach the permissions policy
    aws iam put-role-policy \
      --role-name CodeBuildServiceRole \
      --policy-name CodeBuildServicePolicy \
      --policy-document file://permissions-policy.json

    rm trust-policy.json
    echo "✅ CodeBuildServiceRole created successfully!"
fi

# Clean up temporary files
rm permissions-policy.json

echo "Role ARN: $(aws sts get-caller-identity --query Account --output text | xargs -I {} echo arn:aws:iam::{}:role/CodeBuildServiceRole)"
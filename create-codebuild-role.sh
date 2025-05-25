#!/bin/bash

# Create CodeBuild Service Role
echo "Creating CodeBuildServiceRole..."

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
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
EOF

export AWS_PROFILE=personal
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

# Clean up temporary files
rm trust-policy.json permissions-policy.json

echo "✅ CodeBuildServiceRole created successfully!"
echo "Role ARN: $(aws sts get-caller-identity --query Account --output text | xargs -I {} echo arn:aws:iam::{}:role/CodeBuildServiceRole)"

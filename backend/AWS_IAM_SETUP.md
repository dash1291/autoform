# AWS IAM Setup for Autoform

This guide explains how to set up AWS IAM permissions for teams using Autoform with their own AWS credentials.

## Quick Start

1. **Full Permissions Policy**: Use `aws-iam-policy.json` for complete functionality
2. **Minimal Permissions Policy**: Use `aws-iam-policy-minimal.json` for restricted access

## Required Services

Autoform needs permissions for the following AWS services:

### Core Services (Required)
- **S3**: Store source code for builds
- **ECR**: Container registry for Docker images
- **ECS**: Container orchestration
- **EC2**: Network infrastructure (VPC, subnets, security groups)
- **ELB**: Application load balancers
- **CloudWatch Logs**: Application and build logs
- **CodeBuild**: Build Docker images
- **IAM**: Create service roles

### Optional Services
- **Secrets Manager**: Store environment secrets (if using secret environment variables)
- **STS**: Get caller identity (for validation)

## Setting Up IAM User

### Option 1: Using AWS Console

1. Go to IAM Console → Users → Add User
2. Set username (e.g., `autoform-deployments`)
3. Select "Programmatic access"
4. Click "Next: Permissions"
5. Select "Attach existing policies directly"
6. Click "Create policy" → JSON tab
7. Paste the content from `aws-iam-policy.json`
8. Name the policy (e.g., `AutoformDeploymentPolicy`)
9. Attach the policy to your user
10. Save the Access Key ID and Secret Access Key

### Option 2: Using AWS CLI

```bash
# Create the policy
aws iam create-policy \
  --policy-name AutoformDeploymentPolicy \
  --policy-document file://aws-iam-policy.json

# Create the user
aws iam create-user --user-name autoform-deployments

# Attach the policy (replace ACCOUNT_ID with your AWS account ID)
aws iam attach-user-policy \
  --user-name autoform-deployments \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/AutoformDeploymentPolicy

# Create access keys
aws iam create-access-key --user-name autoform-deployments
```

## Policy Explanations

### Full Permissions (`aws-iam-policy.json`)
- Includes all permissions needed for full platform functionality
- Allows creating new VPCs and infrastructure
- Suitable for teams that want complete control

### Minimal Permissions (`aws-iam-policy-minimal.json`)
- Reduced permissions for security-conscious teams
- Assumes existing VPC/subnets will be used
- May require manual resource creation

## Resource Restrictions

The policies include resource restrictions where possible:

- **S3**: Limited to buckets matching `*-builds-*` pattern
- **IAM**: Limited to specific role patterns
- **CodeBuild**: Limited to projects ending with `-build`
- **Secrets Manager**: Limited to paths starting with `autoform/`
- **CloudWatch Logs**: Limited to `/ecs/*` and `/aws/codebuild/*` paths

## Using Existing Resources

If you want to use existing AWS resources (VPC, subnets, ECS cluster), you can:

1. Use the minimal policy
2. Configure your projects to use existing resources in the UI
3. Grant additional permissions only for the specific resources

Example for existing VPC:
```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:DescribeVpcs",
    "ec2:DescribeSubnets"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "ec2:Vpc": "arn:aws:ec2:region:account-id:vpc/vpc-xxxxx"
    }
  }
}
```

## Security Best Practices

1. **Use IAM Roles** instead of users when possible (e.g., if running Autoform on EC2)
2. **Enable MFA** on the IAM user
3. **Rotate credentials** regularly
4. **Use the minimal policy** and add permissions as needed
5. **Enable CloudTrail** to audit API calls
6. **Restrict by IP** if accessing from known locations:

```json
{
  "Condition": {
    "IpAddress": {
      "aws:SourceIp": ["your-ip-address/32"]
    }
  }
}
```

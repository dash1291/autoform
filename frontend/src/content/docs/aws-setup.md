---
title: AWS Setup Overview
description: Learn how to configure AWS credentials for Autoform deployments
---

# AWS Setup Overview

Learn how to configure AWS credentials for Autoform deployments

>**Security Note:** Autoform encrypts your AWS credentials before storing them.


## Requirements

Before setting up AWS credentials, ensure you have:

- An active AWS account
- AWS Console access
- IAM user creation permissions
- Basic understanding of AWS IAM

## What Autoform Deploys

Autoform will create and manage these AWS resources:

- **VPC** - Virtual Private Cloud for network isolation. This include creating necessary subnets and security groups.
- **ECR** - Container Registry
- **ECS Fargate** - Serverless container hosting
- **ALB** - Application Load Balancer

---

## Setup Instructions

### Step 1: Create IAM User

1. Log into your [AWS Console](https://console.aws.amazon.com)
2. Navigate to **IAM → Users**
3. Click **"Create user"**
4. Enter username: `autoform-deploy`
5. Click **"Next"**

### Step 2: Attach IAM Policy

Create and attach this custom policy for Autoform deployments:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECSManagement",
      "Effect": "Allow",
      "Action": [
        "ecs:*",
        "application-autoscaling:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECSCapacityProviders",
      "Effect": "Allow",
      "Action": [
        "ecs:CreateCapacityProvider",
        "ecs:UpdateCapacityProvider",
        "ecs:DeleteCapacityProvider",
        "ecs:DescribeCapacityProviders",
        "ecs:PutClusterCapacityProviders"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2NetworkManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateVpc",
        "ec2:CreateSubnet",
        "ec2:CreateInternetGateway",
        "ec2:CreateRouteTable",
        "ec2:CreateRoute",
        "ec2:CreateSecurityGroup",
        "ec2:CreateTags",
        "ec2:AttachInternetGateway",
        "ec2:AssociateRouteTable",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:ModifyVpcAttribute",
        "ec2:ModifySubnetAttribute",
        "ec2:CreateLaunchTemplate",
        "ec2:ModifyLaunchTemplate",
        "ec2:DeleteLaunchTemplate",
        "ec2:DescribeLaunchTemplates",
        "ec2:DescribeLaunchTemplateVersions",
        "ec2:RunInstances",
        "ec2:DescribeImages",
        "ec2:Describe*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AutoScalingManagement",
      "Effect": "Allow",
      "Action": [
        "autoscaling:CreateAutoScalingGroup",
        "autoscaling:UpdateAutoScalingGroup",
        "autoscaling:DeleteAutoScalingGroup",
        "autoscaling:DescribeAutoScalingGroups",
        "autoscaling:CreateLaunchConfiguration",
        "autoscaling:DescribeLaunchConfigurations",
        "autoscaling:CreateOrUpdateTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LoadBalancerManagement",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:PassRole",
        "iam:GetRole",
        "iam:CreateInstanceProfile",
        "iam:GetInstanceProfile",
        "iam:AddRoleToInstanceProfile",
        "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies",
        "iam:TagRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRManagement",
      "Effect": "Allow",
      "Action": [
        "ecr:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CodeBuildManagement",
      "Effect": "Allow",
      "Action": [
        "codebuild:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": "*"
    }
  ]
}
```

> This policy provides the necessary permissions for Autoform to deploy applications to AWS ECS.

### Step 3: Create Access Keys

1. Go to your user's **"Security credentials"** tab
2. Scroll to **"Access keys"** section
3. Click **"Create access key"**
4. Select **"Third-party service"**
5. Check the confirmation box and click **"Next"**
6. Add description: `Autoform Deployment`
7. Click **"Create access key"**

> **Important:** Copy both the Access Key ID and Secret Access Key immediately. The secret key won't be shown again after you close this dialog.

### Step 4: Add Credentials to Autoform

1. In Autoform, go to your team's **AWS Settings** tab
2. Enter your **Access Key ID** (starts with AKIA)
3. Enter your **Secret Access Key**
4. Select your preferred **AWS Region**
5. Click **"Save Credentials"**
6. Click **"Test Connection"** to verify everything works

---

## You're All Set!

Once your AWS credentials are configured and tested, you can start deploying your applications. Autoform will automatically create the necessary infrastructure in your AWS account.
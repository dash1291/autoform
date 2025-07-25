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
- **ACM** - SSL certificates for HTTPS domains
- **Route53** - DNS management (optional, for automatic domain validation)

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

{{include-json:backend/aws-iam-policy.json}}

> This policy provides the necessary permissions for Autoform to deploy applications to AWS ECS, including SSL certificate management and optional Route53 DNS automation.

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
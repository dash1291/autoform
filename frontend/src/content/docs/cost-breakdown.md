---
title: AWS Cost Breakdown
description: Understand the costs of resources created by Autoform deployments
---

# AWS Cost Breakdown

## What Autoform Creates

For each deployment, Autoform creates these AWS resources:

- **ECS Fargate Service** - Runs your containerized application
- **Application Load Balancer** - Routes traffic to your app
- **VPC & Subnets** - Network infrastructure (if not using existing)
- **CloudWatch Logs** - Application logs storage
- **ECR Repository** - Stores your Docker images

## Default Configuration

- **CPU**: 0.25 vCPU
- **Memory**: 0.5 GB
- **Storage**: 21 GB

## Example Monthly Cost

For a single application running 24/7 in US East:

```
ECS Fargate (0.25 vCPU, 0.5 GB):  $9/month
Load Balancer:                    $18/month
CloudWatch Logs:                  $0.50/GB ingested + $0.03/GB stored
ECR Storage:                      $0.10/GB per month
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE COST:                        $27/month + usage
```

**AWS Free Tier**: If you're on the free tier, you'll only pay ~$9/month (ALB, CloudWatch up to 5GB, and ECR up to 500MB are free for the first year).

**Regional Pricing**: Costs shown are for US East (N. Virginia). Examples:
- US West (Oregon): ~same
- Europe (Ireland): +10%
- Asia Pacific (Mumbai): -5%
- Asia Pacific (Sydney): +10-15%

**Note**: Costs are billed directly to your AWS account. Autoform doesn't add any markup.
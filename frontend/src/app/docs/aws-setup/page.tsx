import { getDocBySlug } from '@/lib/docs'
import { notFound } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import { CodeBlock } from '@/components/ui/code-block'

const awsIamPolicy = {
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

export default async function AwsSetupPage() {
  const doc = await getDocBySlug('aws-setup')
  
  if (!doc) {
    notFound()
  }

  return (
    <AuthGuard>
      <div className="prose prose-gray max-w-none">
        <div dangerouslySetInnerHTML={{ __html: doc.content }} />
      </div>
    </AuthGuard>
  )
}
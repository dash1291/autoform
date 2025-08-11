import json
import logging
from typing import Tuple
from utils.aws_client import create_client

logger = logging.getLogger(__name__)


class IAMService:
    def __init__(
        self, project_name: str, region: str = "us-east-1", aws_credentials=None
    ):
        self.project_name = project_name
        self.region = region
        self.aws_credentials = aws_credentials

        # Initialize AWS clients with custom credentials if provided
        self.iam = create_client("iam", region, aws_credentials)
        self.sts = create_client("sts", region, aws_credentials)

        self.execution_role_arn: str = ""
        self.task_role_arn: str = ""
        self.codebuild_role_arn: str = ""

    async def initialize(self):
        """Initialize IAM roles"""
        self.execution_role_arn = await self._create_execution_role()
        self.task_role_arn = await self._create_task_role()
        self.codebuild_role_arn = await self._create_codebuild_role()

    async def _get_account_id(self) -> str:
        """Get AWS account ID"""
        response = self.sts.get_caller_identity()
        return response["Account"]

    async def _create_execution_role(self) -> str:
        """Create ECS task execution role"""
        role_name = f"{self.project_name}-ecs-execution-role"

        try:
            # Check if role exists
            response = self.iam.get_role(RoleName=role_name)
            logger.info(f"Found existing execution role: {response['Role']['Arn']}")
            return response["Role"]["Arn"]
        except self.iam.exceptions.NoSuchEntityException:
            pass

        # Create new role
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        response = self.iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "Name", "Value": role_name}],
        )

        role_arn = response["Role"]["Arn"]

        # Attach policies
        policies = [
            "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
        ]

        for policy_arn in policies:
            self.iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)

        # Create and attach inline policy for Secrets Manager
        secrets_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue",
                        "secretsmanager:DescribeSecret",
                    ],
                    "Resource": f"arn:aws:secretsmanager:{self.region}:*:secret:autoform/*",
                }
            ],
        }

        self.iam.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{self.project_name}-secrets-access",
            PolicyDocument=json.dumps(secrets_policy),
        )

        logger.info(f"Created execution role: {role_arn}")
        return role_arn

    async def _create_task_role(self) -> str:
        """Create ECS task role"""
        role_name = f"{self.project_name}-ecs-task-role"

        try:
            # Check if role exists
            response = self.iam.get_role(RoleName=role_name)
            logger.info(f"Found existing task role: {response['Role']['Arn']}")
            return response["Role"]["Arn"]
        except self.iam.exceptions.NoSuchEntityException:
            pass

        # Create new role
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        response = self.iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "Name", "Value": role_name}],
        )

        role_arn = response["Role"]["Arn"]

        # Add policies for ECS Exec
        exec_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ssmmessages:CreateControlChannel",
                        "ssmmessages:CreateDataChannel",
                        "ssmmessages:OpenControlChannel",
                        "ssmmessages:OpenDataChannel",
                    ],
                    "Resource": "*",
                }
            ],
        }

        self.iam.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{self.project_name}-ecs-exec",
            PolicyDocument=json.dumps(exec_policy),
        )

        logger.info(f"Created task role: {role_arn}")
        return role_arn

    async def _create_codebuild_role(self) -> str:
        """Create CodeBuild service role"""
        role_name = f"{self.project_name}-codebuild-role"
        account_id = await self._get_account_id()

        try:
            # Check if role exists
            response = self.iam.get_role(RoleName=role_name)
            logger.info(f"Found existing CodeBuild role: {response['Role']['Arn']}")
            return response["Role"]["Arn"]
        except self.iam.exceptions.NoSuchEntityException:
            pass

        # Create new role
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "codebuild.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        response = self.iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Tags=[{"Key": "Name", "Value": role_name}],
        )

        role_arn = response["Role"]["Arn"]

        # Create and attach inline policy
        codebuild_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    "Resource": f"arn:aws:logs:{self.region}:{account_id}:log-group:/aws/codebuild/*",
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject"],
                    "Resource": [
                        f"arn:aws:s3:::{self.project_name.lower()}-builds-{self.region}/*",
                        f"arn:aws:s3:::codebuild-{self.region}-{account_id}-*/*",
                        # Add wildcard pattern to handle various project name formats
                        f"arn:aws:s3:::*-builds-{self.region}/*"
                    ],
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": [
                        f"arn:aws:s3:::{self.project_name.lower()}-builds-{self.region}",
                        f"arn:aws:s3:::codebuild-{self.region}-{account_id}-*",
                        # Add wildcard pattern to handle various project name formats
                        f"arn:aws:s3:::*-builds-{self.region}"
                    ],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "ecr:GetAuthorizationToken",
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage",
                        "ecr:PutImage",
                        "ecr:InitiateLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:CompleteLayerUpload",
                    ],
                    "Resource": "*",
                },
            ],
        }

        self.iam.put_role_policy(
            RoleName=role_name,
            PolicyName=f"{self.project_name}-codebuild-policy",
            PolicyDocument=json.dumps(codebuild_policy),
        )

        logger.info(f"Created CodeBuild role: {role_arn}")
        return role_arn

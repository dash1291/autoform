import logging
import boto3
from typing import Optional, Dict, List
from botocore.exceptions import ClientError
from utils.aws_client import create_client
from models.project import Project
from models.environment import Environment
from core.database import get_async_session
from sqlmodel import select

logger = logging.getLogger(__name__)


class ProjectDeletionService:
    """Service for deleting project infrastructure while preserving shared resources"""
    
    def __init__(self, region: str, aws_credentials: Optional[dict] = None):
        self.region = region
        self.aws_credentials = aws_credentials
        
        # Initialize AWS clients
        self.ecs = create_client("ecs", region, aws_credentials)
        self.elbv2 = create_client("elbv2", region, aws_credentials)
        self.ec2 = create_client("ec2", region, aws_credentials)
        self.logs = create_client("logs", region, aws_credentials)
        self.ecr = create_client("ecr", region, aws_credentials)
        self.s3 = create_client("s3", region, aws_credentials)
        self.secretsmanager = create_client("secretsmanager", region, aws_credentials)
        
    async def delete_project_infrastructure(self, project_id: str) -> Dict[str, any]:
        """
        Delete all project-specific infrastructure
        Returns a summary of deleted resources
        """
        deletion_summary = {
            "success": True,
            "deleted_resources": [],
            "failed_resources": [],
            "errors": []
        }
        
        try:
            # Get project and all its environments
            async with get_async_session() as session:
                project_result = await session.execute(
                    select(Project).where(Project.id == project_id)
                )
                project = project_result.scalar_one_or_none()
                
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                # Get all environments for this project
                env_result = await session.execute(
                    select(Environment).where(Environment.project_id == project_id)
                )
                environments = env_result.scalars().all()
            
            # Delete infrastructure for each environment
            for environment in environments:
                logger.info(f"Deleting infrastructure for environment: {environment.name}")
                env_deletion = await self._delete_environment_infrastructure(environment, project.name)
                deletion_summary["deleted_resources"].extend(env_deletion.get("deleted", []))
                deletion_summary["failed_resources"].extend(env_deletion.get("failed", []))
                if env_deletion.get("errors"):
                    deletion_summary["errors"].extend(env_deletion["errors"])
            
            # Delete project-level resources (legacy deployments)
            if project.ecs_service_arn or project.alb_arn:
                logger.info(f"Deleting legacy project-level infrastructure")
                project_deletion = await self._delete_project_level_infrastructure(project)
                deletion_summary["deleted_resources"].extend(project_deletion.get("deleted", []))
                deletion_summary["failed_resources"].extend(project_deletion.get("failed", []))
                if project_deletion.get("errors"):
                    deletion_summary["errors"].extend(project_deletion["errors"])
            
            # Delete ECR repository
            ecr_deletion = await self._delete_ecr_repository(project.name)
            if ecr_deletion["success"]:
                deletion_summary["deleted_resources"].append(ecr_deletion["resource"])
            else:
                deletion_summary["failed_resources"].append(ecr_deletion["resource"])
                if ecr_deletion.get("error"):
                    deletion_summary["errors"].append(ecr_deletion["error"])
            
            # Delete CloudWatch log groups
            log_deletion = await self._delete_log_groups(project.name)
            deletion_summary["deleted_resources"].extend(log_deletion.get("deleted", []))
            deletion_summary["failed_resources"].extend(log_deletion.get("failed", []))
            
            # Delete S3 build artifacts bucket
            s3_deletion = await self._delete_s3_bucket(project.name)
            if s3_deletion["success"]:
                deletion_summary["deleted_resources"].append(s3_deletion["resource"])
            else:
                deletion_summary["failed_resources"].append(s3_deletion["resource"])
            
            deletion_summary["success"] = len(deletion_summary["failed_resources"]) == 0
            
        except Exception as e:
            logger.error(f"Error deleting project infrastructure: {e}")
            deletion_summary["success"] = False
            deletion_summary["errors"].append(str(e))
        
        return deletion_summary
    
    async def _delete_environment_infrastructure(self, environment: Environment, project_name: str) -> Dict:
        """Delete infrastructure for a specific environment"""
        result = {"deleted": [], "failed": [], "errors": []}
        
        try:
            # 1. Delete ECS Service
            if environment.ecs_service_arn:
                service_deletion = await self._delete_ecs_service(
                    environment.ecs_service_arn,
                    environment.ecs_cluster_arn
                )
                if service_deletion["success"]:
                    result["deleted"].append(service_deletion["resource"])
                else:
                    result["failed"].append(service_deletion["resource"])
                    if service_deletion.get("error"):
                        result["errors"].append(service_deletion["error"])
            
            # 2. Delete Load Balancer and Target Groups
            if environment.alb_arn:
                alb_deletion = await self._delete_load_balancer(environment.alb_arn)
                if alb_deletion["success"]:
                    result["deleted"].extend(alb_deletion["deleted_resources"])
                else:
                    result["failed"].extend(alb_deletion["failed_resources"])
                    if alb_deletion.get("errors"):
                        result["errors"].extend(alb_deletion["errors"])
            
            # 3. Delete Security Groups (only project-specific ones)
            sg_deletion = await self._delete_security_groups(project_name, environment.name)
            result["deleted"].extend(sg_deletion.get("deleted", []))
            result["failed"].extend(sg_deletion.get("failed", []))
            
            # 4. Delete Secrets
            secrets_deletion = await self._delete_secrets(project_name)
            result["deleted"].extend(secrets_deletion.get("deleted", []))
            result["failed"].extend(secrets_deletion.get("failed", []))
            
        except Exception as e:
            logger.error(f"Error deleting environment infrastructure: {e}")
            result["errors"].append(str(e))
        
        return result
    
    async def _delete_project_level_infrastructure(self, project: Project) -> Dict:
        """Delete legacy project-level infrastructure"""
        result = {"deleted": [], "failed": [], "errors": []}
        
        try:
            # Delete ECS Service
            if project.ecs_service_arn:
                service_deletion = await self._delete_ecs_service(
                    project.ecs_service_arn,
                    project.ecs_cluster_arn
                )
                if service_deletion["success"]:
                    result["deleted"].append(service_deletion["resource"])
                else:
                    result["failed"].append(service_deletion["resource"])
            
            # Delete Load Balancer
            if project.alb_arn:
                alb_deletion = await self._delete_load_balancer(project.alb_arn)
                if alb_deletion["success"]:
                    result["deleted"].extend(alb_deletion["deleted_resources"])
                else:
                    result["failed"].extend(alb_deletion["failed_resources"])
            
            # Delete Security Groups
            sg_deletion = await self._delete_security_groups(project.name)
            result["deleted"].extend(sg_deletion.get("deleted", []))
            result["failed"].extend(sg_deletion.get("failed", []))
            
        except Exception as e:
            logger.error(f"Error deleting project-level infrastructure: {e}")
            result["errors"].append(str(e))
        
        return result
    
    async def _delete_ecs_service(self, service_arn: str, cluster_arn: Optional[str]) -> Dict:
        """Delete an ECS service"""
        try:
            if not cluster_arn:
                logger.warning(f"No cluster ARN provided for service {service_arn}")
                return {"success": False, "resource": f"ECS Service: {service_arn}", "error": "No cluster ARN"}
            
            # Extract identifiers from ARNs
            service_name = service_arn.split("/")[-1] if "/" in service_arn else service_arn
            cluster_name = cluster_arn.split("/")[-1] if "/" in cluster_arn else cluster_arn
            
            # First, update service to have 0 desired count
            logger.info(f"Scaling down ECS service: {service_name}")
            self.ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                desiredCount=0
            )
            
            # Delete the service
            logger.info(f"Deleting ECS service: {service_name}")
            self.ecs.delete_service(
                cluster=cluster_name,
                service=service_name,
                force=True  # Force delete even if there are active tasks
            )
            
            return {"success": True, "resource": f"ECS Service: {service_name}"}
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ServiceNotFoundException":
                logger.info(f"ECS service already deleted: {service_arn}")
                return {"success": True, "resource": f"ECS Service: {service_arn} (already deleted)"}
            logger.error(f"Error deleting ECS service: {e}")
            return {"success": False, "resource": f"ECS Service: {service_arn}", "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error deleting ECS service: {e}")
            return {"success": False, "resource": f"ECS Service: {service_arn}", "error": str(e)}
    
    async def _delete_load_balancer(self, alb_arn: str) -> Dict:
        """Delete load balancer and its associated resources"""
        result = {"success": True, "deleted_resources": [], "failed_resources": [], "errors": []}
        
        try:
            # Get load balancer details
            lb_response = self.elbv2.describe_load_balancers(LoadBalancerArns=[alb_arn])
            if not lb_response["LoadBalancers"]:
                result["deleted_resources"].append(f"Load Balancer: {alb_arn} (already deleted)")
                return result
            
            lb = lb_response["LoadBalancers"][0]
            lb_name = lb["LoadBalancerName"]
            
            # Get and delete all listeners
            listeners_response = self.elbv2.describe_listeners(LoadBalancerArn=alb_arn)
            for listener in listeners_response["Listeners"]:
                try:
                    logger.info(f"Deleting listener: {listener['ListenerArn']}")
                    self.elbv2.delete_listener(ListenerArn=listener["ListenerArn"])
                    result["deleted_resources"].append(f"Listener: {listener['ListenerArn']}")
                except ClientError as e:
                    logger.error(f"Error deleting listener: {e}")
                    result["failed_resources"].append(f"Listener: {listener['ListenerArn']}")
                    result["errors"].append(str(e))
            
            # Get and delete target groups
            tg_response = self.elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
            for tg in tg_response["TargetGroups"]:
                try:
                    logger.info(f"Deleting target group: {tg['TargetGroupName']}")
                    self.elbv2.delete_target_group(TargetGroupArn=tg["TargetGroupArn"])
                    result["deleted_resources"].append(f"Target Group: {tg['TargetGroupName']}")
                except ClientError as e:
                    logger.error(f"Error deleting target group: {e}")
                    result["failed_resources"].append(f"Target Group: {tg['TargetGroupName']}")
                    result["errors"].append(str(e))
            
            # Delete the load balancer
            logger.info(f"Deleting load balancer: {lb_name}")
            self.elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
            result["deleted_resources"].append(f"Load Balancer: {lb_name}")
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "LoadBalancerNotFound":
                result["deleted_resources"].append(f"Load Balancer: {alb_arn} (already deleted)")
            else:
                logger.error(f"Error deleting load balancer: {e}")
                result["failed_resources"].append(f"Load Balancer: {alb_arn}")
                result["errors"].append(str(e))
                result["success"] = False
        except Exception as e:
            logger.error(f"Unexpected error deleting load balancer: {e}")
            result["failed_resources"].append(f"Load Balancer: {alb_arn}")
            result["errors"].append(str(e))
            result["success"] = False
        
        return result
    
    async def _delete_security_groups(self, project_name: str, environment_name: Optional[str] = None) -> Dict:
        """Delete project-specific security groups"""
        result = {"deleted": [], "failed": []}
        
        try:
            # Build security group name patterns
            if environment_name:
                sg_patterns = [
                    f"{project_name}-{environment_name}-alb-sg",
                    f"{project_name}-{environment_name}-ecs-sg",
                ]
            else:
                sg_patterns = [
                    f"{project_name}-alb-sg",
                    f"{project_name}-ecs-sg",
                ]
            
            # Search for security groups by name
            sg_response = self.ec2.describe_security_groups(
                Filters=[
                    {
                        "Name": "group-name",
                        "Values": sg_patterns
                    }
                ]
            )
            
            for sg in sg_response["SecurityGroups"]:
                try:
                    logger.info(f"Deleting security group: {sg['GroupName']} ({sg['GroupId']})")
                    self.ec2.delete_security_group(GroupId=sg["GroupId"])
                    result["deleted"].append(f"Security Group: {sg['GroupName']}")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    if error_code == "InvalidGroup.NotFound":
                        result["deleted"].append(f"Security Group: {sg['GroupName']} (already deleted)")
                    else:
                        logger.error(f"Error deleting security group {sg['GroupName']}: {e}")
                        result["failed"].append(f"Security Group: {sg['GroupName']}")
            
        except Exception as e:
            logger.error(f"Error deleting security groups: {e}")
        
        return result
    
    async def _delete_ecr_repository(self, project_name: str) -> Dict:
        """Delete ECR repository"""
        try:
            repository_name = project_name.lower().replace("[^a-z0-9-_]", "-")
            
            logger.info(f"Deleting ECR repository: {repository_name}")
            self.ecr.delete_repository(
                repositoryName=repository_name,
                force=True  # Delete even if it contains images
            )
            
            return {"success": True, "resource": f"ECR Repository: {repository_name}"}
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "RepositoryNotFoundException":
                logger.info(f"ECR repository already deleted: {repository_name}")
                return {"success": True, "resource": f"ECR Repository: {repository_name} (already deleted)"}
            logger.error(f"Error deleting ECR repository: {e}")
            return {"success": False, "resource": f"ECR Repository: {repository_name}", "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error deleting ECR repository: {e}")
            return {"success": False, "resource": f"ECR Repository: {repository_name}", "error": str(e)}
    
    async def _delete_log_groups(self, project_name: str) -> Dict:
        """Delete CloudWatch log groups"""
        result = {"deleted": [], "failed": []}
        
        try:
            # Log group patterns to delete
            log_group_patterns = [
                f"/ecs/{project_name}",
                f"/aws/codebuild/{project_name}-build",
            ]
            
            for log_group_name in log_group_patterns:
                try:
                    logger.info(f"Deleting log group: {log_group_name}")
                    self.logs.delete_log_group(logGroupName=log_group_name)
                    result["deleted"].append(f"Log Group: {log_group_name}")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    if error_code == "ResourceNotFoundException":
                        result["deleted"].append(f"Log Group: {log_group_name} (already deleted)")
                    else:
                        logger.error(f"Error deleting log group {log_group_name}: {e}")
                        result["failed"].append(f"Log Group: {log_group_name}")
            
        except Exception as e:
            logger.error(f"Error deleting log groups: {e}")
        
        return result
    
    async def _delete_s3_bucket(self, project_name: str) -> Dict:
        """Delete S3 bucket used for build artifacts"""
        try:
            bucket_name = f"{project_name.lower().replace('[^a-z0-9-]', '-')}-builds-{self.region}"
            
            # First, delete all objects in the bucket
            logger.info(f"Emptying S3 bucket: {bucket_name}")
            paginator = self.s3.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=bucket_name)
            
            delete_keys = []
            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        delete_keys.append({"Key": obj["Key"]})
            
            if delete_keys:
                # Delete objects in batches of 1000 (S3 limit)
                for i in range(0, len(delete_keys), 1000):
                    batch = delete_keys[i:i+1000]
                    self.s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": batch}
                    )
            
            # Delete the bucket
            logger.info(f"Deleting S3 bucket: {bucket_name}")
            self.s3.delete_bucket(Bucket=bucket_name)
            
            return {"success": True, "resource": f"S3 Bucket: {bucket_name}"}
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchBucket":
                logger.info(f"S3 bucket already deleted: {bucket_name}")
                return {"success": True, "resource": f"S3 Bucket: {bucket_name} (already deleted)"}
            logger.error(f"Error deleting S3 bucket: {e}")
            return {"success": False, "resource": f"S3 Bucket: {bucket_name}", "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error deleting S3 bucket: {e}")
            return {"success": False, "resource": f"S3 Bucket: {bucket_name}", "error": str(e)}
    
    async def _delete_secrets(self, project_name: str) -> Dict:
        """Delete secrets from AWS Secrets Manager"""
        result = {"deleted": [], "failed": []}
        
        try:
            # List secrets with project prefix
            paginator = self.secretsmanager.get_paginator("list_secrets")
            page_iterator = paginator.paginate(
                Filters=[
                    {
                        "Key": "name",
                        "Values": [f"{project_name}/"]
                    }
                ]
            )
            
            for page in page_iterator:
                for secret in page.get("SecretList", []):
                    try:
                        secret_name = secret["Name"]
                        logger.info(f"Deleting secret: {secret_name}")
                        self.secretsmanager.delete_secret(
                            SecretId=secret["ARN"],
                            ForceDeleteWithoutRecovery=True
                        )
                        result["deleted"].append(f"Secret: {secret_name}")
                    except ClientError as e:
                        logger.error(f"Error deleting secret {secret_name}: {e}")
                        result["failed"].append(f"Secret: {secret_name}")
            
        except Exception as e:
            logger.error(f"Error deleting secrets: {e}")
        
        return result
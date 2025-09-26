import logging
from typing import List, Optional
from utils.aws_client import create_client
from .acm_service import ACMService

logger = logging.getLogger(__name__)


class LoadBalancerService:
    def __init__(
        self,
        project_name: str,
        region: str = "us-east-1",
        vpc_id: str = "",
        subnet_ids: List[str] = None,
        security_group_id: str = "",
        container_port: int = 3000,
        health_check_path: str = "/",
        aws_credentials=None,
        certificate_arn: str = None,
        redirect_http_to_https: bool = True,
        domain_name: Optional[str] = None,
        auto_provision_certificate: bool = True,
        use_route53_validation: bool = True,
    ):
        self.project_name = project_name
        self.region = region
        self.vpc_id = vpc_id
        self.subnet_ids = subnet_ids or []
        self.security_group_id = security_group_id
        self.container_port = container_port
        self.health_check_path = health_check_path
        self.aws_credentials = aws_credentials
        self.certificate_arn = certificate_arn
        self.redirect_http_to_https = redirect_http_to_https
        self.domain_name = domain_name
        self.auto_provision_certificate = auto_provision_certificate
        self.use_route53_validation = use_route53_validation

        # Initialize ELBv2 client with custom credentials if provided
        self.elbv2 = create_client("elbv2", region, aws_credentials)
        
        # Initialize ACM service if needed
        self.acm_service = None
        if domain_name and auto_provision_certificate and not certificate_arn:
            self.acm_service = ACMService(
                project_name=project_name,
                domain_name=domain_name,
                region=region,
                aws_credentials=aws_credentials,
                use_route53_validation=use_route53_validation,
            )

        self.load_balancer_arn: str = ""
        self.load_balancer_dns: str = ""
        self.load_balancer_name: str = ""
        self.target_group_arn: str = ""
        self.listener_arn: str = ""
        self.https_listener_arn: str = ""

    async def initialize(self):
        """Initialize Load Balancer resources"""
        # Auto-provision certificate if needed
        if self.domain_name and self.auto_provision_certificate and not self.certificate_arn:
            logger.info(f"Auto-provisioning certificate for domain: {self.domain_name}")
            if self.acm_service:
                try:
                    # During deployment, wait for validation to complete
                    self.certificate_arn = await self.acm_service.get_or_create_certificate(wait_for_validation=True)
                    logger.info(f"Certificate provisioned successfully: {self.certificate_arn}")
                except Exception as e:
                    logger.error(f"Failed to auto-provision certificate: {e}")
                    logger.warning("Continuing without HTTPS...")
        
        # Create or find load balancer
        lb_result = await self._create_or_find_load_balancer()
        self.load_balancer_arn = lb_result["arn"]
        self.load_balancer_dns = lb_result["dns"]

        # Create target group
        self.target_group_arn = await self._create_target_group()

        # Create listener
        self.listener_arn = await self._create_listener()
        
        # Create DNS record if domain is configured
        if self.domain_name and self.acm_service and self.load_balancer_dns:
            logger.info(f"Creating DNS record for {self.domain_name} -> {self.load_balancer_dns}")
            await self.acm_service.create_dns_record_for_load_balancer(self.load_balancer_dns)

    async def _create_or_find_load_balancer(self) -> dict:
        """Create or find Application Load Balancer"""
        lb_name = self.project_name
        self.load_balancer_name = lb_name

        try:
            # Check if load balancer already exists
            response = self.elbv2.describe_load_balancers(Names=[lb_name])

            if response["LoadBalancers"] and len(response["LoadBalancers"]) > 0:
                lb = response["LoadBalancers"][0]
                logger.info(f"Found existing load balancer: {lb['LoadBalancerArn']}")
                
                # Log the subnets the existing load balancer is using
                existing_lb_subnets = [az['SubnetId'] for az in lb.get('AvailabilityZones', [])]
                logger.warning(f"⚠️  Existing load balancer is using subnets: {existing_lb_subnets}")
                logger.warning(f"⚠️  Requested subnets were: {self.subnet_ids}")
                
                if set(existing_lb_subnets) != set(self.subnet_ids):
                    logger.error("❌ SUBNET MISMATCH: Existing load balancer is in different subnets than requested!")
                    logger.error(f"   Existing ALB subnets: {existing_lb_subnets}")
                    logger.error(f"   Requested subnets: {self.subnet_ids}")
                    raise Exception(
                        f"Existing load balancer '{lb_name}' is in different subnets than requested. "
                        f"ALB is in subnets {existing_lb_subnets} but ECS will use {self.subnet_ids}. "
                        f"This will cause networking issues. Please delete the existing load balancer or use the same subnets."
                    )
                
                return {"arn": lb["LoadBalancerArn"], "dns": lb["DNSName"]}
        except self.elbv2.exceptions.LoadBalancerNotFoundException:
            logger.info("No existing load balancer found, creating new one")
        except Exception as e:
            if "different subnets than requested" in str(e):
                raise  # Re-raise our subnet mismatch error
            logger.info(f"Error checking for existing load balancer: {e}")

        # Create new load balancer
        logger.info(f"🔍 Creating load balancer '{lb_name}' with subnets: {self.subnet_ids}")
        response = self.elbv2.create_load_balancer(
            Name=lb_name,
            Subnets=self.subnet_ids,
            SecurityGroups=[self.security_group_id],
            Tags=[{"Key": "Name", "Value": lb_name}],
        )

        lb = response["LoadBalancers"][0]
        logger.info(f"Created new load balancer: {lb['LoadBalancerArn']}")

        return {"arn": lb["LoadBalancerArn"], "dns": lb["DNSName"]}

    async def _create_target_group(self) -> str:
        """Create Target Group for the load balancer"""
        # Apply name shortening logic to keep under 32 character limit
        tg_name = self.project_name
        if len(tg_name) > 32:
            tg_name = tg_name[:32]
            logger.info(f"Target group name truncated to: {tg_name}")
        
        tg_name_to_create = tg_name

        try:
            # Check if target group already exists
            response = self.elbv2.describe_target_groups(Names=[tg_name])

            if response["TargetGroups"] and len(response["TargetGroups"]) > 0:
                existing_tg = response["TargetGroups"][0]
                logger.info(
                    f"Found existing target group: {existing_tg['TargetGroupArn']}"
                )
                
                # Check if the target group is in the same VPC and has correct target type
                existing_tg_vpc = existing_tg.get('VpcId')
                existing_tg_type = existing_tg.get('TargetType')
                logger.info(f"🔍 Existing target group VPC: {existing_tg_vpc}, Expected VPC: {self.vpc_id}")
                logger.info(f"🔍 Existing target group type: {existing_tg_type}, Expected type: ip")
                
                if existing_tg_vpc != self.vpc_id:
                    logger.warning(f"⚠️  Existing target group is in different VPC ({existing_tg_vpc}) than expected ({self.vpc_id})")
                    logger.info("Creating new target group in the correct VPC")
                    # Don't return, let it fall through to create a new one
                elif existing_tg_type != 'ip':
                    # This is a corner case with inconsistent infrastructure
                    logger.warning(f"⚠️  Existing target group has incorrect target type ({existing_tg_type}) - expected 'ip' for Fargate")
                    logger.warning("This appears to be legacy infrastructure. Creating a new target group with '-ip' suffix.")
                    # Create with a different name to avoid conflicts
                    tg_name_to_create = f"{tg_name}-ip"
                    if len(tg_name_to_create) > 32:
                        tg_name_to_create = tg_name_to_create[:32]
                    logger.info(f"Will create new target group with name: {tg_name_to_create}")
                    # Don't return, let it fall through to create a new one
                else:
                    # Update the target group attributes to ensure correct health check settings
                    await self._update_target_group_attributes(
                        existing_tg["TargetGroupArn"]
                    )
                    return existing_tg["TargetGroupArn"]
        except Exception:
            logger.info("No existing target group found, creating new one")

        # Create new target group
        response = self.elbv2.create_target_group(
            Name=tg_name_to_create,
            Port=self.container_port,
            Protocol="HTTP",
            VpcId=self.vpc_id,
            TargetType="ip",
            HealthCheckEnabled=True,
            HealthCheckIntervalSeconds=30,
            HealthCheckPath=self.health_check_path,
            HealthCheckPort="traffic-port",
            HealthCheckProtocol="HTTP",
            HealthCheckTimeoutSeconds=5,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=2,
            Matcher={"HttpCode": "200"},
            Tags=[
                {"Key": "Name", "Value": tg_name_to_create},
                {"Key": "Project", "Value": self.project_name},
                {"Key": "ManagedBy", "Value": "AutoForm"}
            ],
        )

        target_group = response["TargetGroups"][0]
        logger.info(f"Created target group: {target_group['TargetGroupArn']}")
        return target_group["TargetGroupArn"]

    async def _update_target_group_attributes(self, target_group_arn: str):
        """Update target group health check settings"""
        try:
            # Update health check settings to ensure they match our requirements
            self.elbv2.modify_target_group(
                TargetGroupArn=target_group_arn,
                HealthCheckEnabled=True,
                HealthCheckIntervalSeconds=30,
                HealthCheckPath=self.health_check_path,
                HealthCheckPort="traffic-port",
                HealthCheckProtocol="HTTP",
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=2,
                Matcher={"HttpCode": "200"},
            )

            logger.info("Updated target group health check settings")
        except Exception as error:
            logger.warning(f"Failed to update target group attributes: {error}")
            # Don't fail deployment if we can't update attributes

    async def _create_listener(self) -> str:
        """Create listener(s) for the load balancer"""
        # Create HTTP listener
        self.listener_arn = await self._create_http_listener()
        
        # Create HTTPS listener if certificate is provided
        if self.certificate_arn:
            self.https_listener_arn = await self._create_https_listener()
            logger.info(f"HTTPS listener created with certificate: {self.certificate_arn}")
        
        return self.listener_arn

    async def _create_http_listener(self) -> str:
        """Create HTTP listener"""
        try:
            # Check if HTTP listener already exists
            response = self.elbv2.describe_listeners(
                LoadBalancerArn=self.load_balancer_arn
            )

            for listener in response.get("Listeners", []):
                if listener.get("Port") == 80:
                    # Update existing HTTP listener
                    if self.redirect_http_to_https and self.certificate_arn:
                        # Configure redirect to HTTPS
                        self.elbv2.modify_listener(
                            ListenerArn=listener["ListenerArn"],
                            DefaultActions=[{
                                "Type": "redirect",
                                "RedirectConfig": {
                                    "Protocol": "HTTPS",
                                    "Port": "443",
                                    "StatusCode": "HTTP_301"
                                }
                            }],
                        )
                        logger.info(f"Updated HTTP listener to redirect to HTTPS: {listener['ListenerArn']}")
                    else:
                        # Forward to target group
                        self.elbv2.modify_listener(
                            ListenerArn=listener["ListenerArn"],
                            DefaultActions=[
                                {"Type": "forward", "TargetGroupArn": self.target_group_arn}
                            ],
                        )
                        logger.info(f"Updated existing HTTP listener: {listener['ListenerArn']}")
                    return listener["ListenerArn"]
        except Exception as e:
            logger.info(f"Error checking for existing HTTP listener: {e}")

        # Create new HTTP listener
        if self.redirect_http_to_https and self.certificate_arn:
            # Create with redirect action
            default_actions = [{
                "Type": "redirect",
                "RedirectConfig": {
                    "Protocol": "HTTPS",
                    "Port": "443",
                    "StatusCode": "HTTP_301"
                }
            }]
        else:
            # Create with forward action
            default_actions = [
                {"Type": "forward", "TargetGroupArn": self.target_group_arn}
            ]

        response = self.elbv2.create_listener(
            LoadBalancerArn=self.load_balancer_arn,
            Port=80,
            Protocol="HTTP",
            DefaultActions=default_actions,
            Tags=[{"Key": "Name", "Value": f"{self.project_name}-http-listener"}],
        )

        listener = response["Listeners"][0]
        logger.info(f"Created new HTTP listener: {listener['ListenerArn']}")
        return listener["ListenerArn"]

    async def _create_https_listener(self) -> str:
        """Create HTTPS listener"""
        try:
            # Check if HTTPS listener already exists
            response = self.elbv2.describe_listeners(
                LoadBalancerArn=self.load_balancer_arn
            )

            for listener in response.get("Listeners", []):
                if listener.get("Port") == 443:
                    # Update existing HTTPS listener
                    self.elbv2.modify_listener(
                        ListenerArn=listener["ListenerArn"],
                        Certificates=[{"CertificateArn": self.certificate_arn}],
                        DefaultActions=[
                            {"Type": "forward", "TargetGroupArn": self.target_group_arn}
                        ],
                    )
                    logger.info(f"Updated existing HTTPS listener: {listener['ListenerArn']}")
                    return listener["ListenerArn"]
        except Exception as e:
            logger.info(f"Error checking for existing HTTPS listener: {e}")

        # Create new HTTPS listener
        response = self.elbv2.create_listener(
            LoadBalancerArn=self.load_balancer_arn,
            Port=443,
            Protocol="HTTPS",
            Certificates=[{"CertificateArn": self.certificate_arn}],
            DefaultActions=[
                {"Type": "forward", "TargetGroupArn": self.target_group_arn}
            ],
            Tags=[{"Key": "Name", "Value": f"{self.project_name}-https-listener"}],
        )

        listener = response["Listeners"][0]
        logger.info(f"Created new HTTPS listener: {listener['ListenerArn']}")
        return listener["ListenerArn"]

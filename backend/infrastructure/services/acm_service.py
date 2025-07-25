import logging
import time
from typing import Optional, List, Dict
from utils.aws_client import create_client

logger = logging.getLogger(__name__)


class ACMService:
    def __init__(
        self,
        project_name: str,
        domain_name: str,
        region: str = "us-east-1",
        aws_credentials=None,
        use_route53_validation: bool = True,
    ):
        self.project_name = project_name
        self.domain_name = domain_name
        self.region = region
        self.aws_credentials = aws_credentials
        self.use_route53_validation = use_route53_validation
        
        # Initialize AWS clients
        self.acm = create_client("acm", region, aws_credentials)
        self.route53 = create_client("route53", region, aws_credentials) if use_route53_validation else None
        
        self.certificate_arn: Optional[str] = None
        self.validation_records: List[Dict] = []

    async def get_or_create_certificate(self, wait_for_validation: bool = False) -> str:
        """Get existing certificate or create a new one"""
        # First, check if a certificate already exists for this domain
        existing_cert = await self._find_existing_certificate()
        if existing_cert:
            logger.info(f"Found existing certificate: {existing_cert}")
            self.certificate_arn = existing_cert
            return existing_cert
        
        # Create new certificate
        logger.info(f"Creating new certificate for domain: {self.domain_name}")
        self.certificate_arn = await self._request_certificate()
        
        # Get validation records
        await self._get_validation_records()
        
        # Auto-validate if using Route53
        if self.use_route53_validation:
            try:
                await self._auto_validate_with_route53()
                logger.info("Route53 validation configured successfully")
            except Exception as e:
                logger.error(f"Route53 validation failed: {e}")
                logger.warning("Falling back to manual DNS validation. Please add these CNAME records:")
                for record in self.validation_records:
                    logger.warning(f"  Name: {record['Name']} -> Value: {record['Value']}")
        else:
            # Return validation records for manual setup
            logger.warning(f"Manual DNS validation required. Add these CNAME records to your DNS:")
            for record in self.validation_records:
                logger.warning(f"  Name: {record['Name']} -> Value: {record['Value']}")
        
        # Only wait for validation if explicitly requested (e.g., during deployment)
        if wait_for_validation:
            await self._wait_for_validation()
        else:
            logger.info(f"Certificate requested: {self.certificate_arn}. Validation will continue in background.")
        
        return self.certificate_arn

    async def _find_existing_certificate(self) -> Optional[str]:
        """Find existing certificate for the domain"""
        try:
            paginator = self.acm.get_paginator('list_certificates')
            
            for page in paginator.paginate(CertificateStatuses=['ISSUED']):
                for cert in page.get('CertificateSummaryList', []):
                    cert_arn = cert['CertificateArn']
                    cert_domain = cert['DomainName']
                    
                    # Check if this certificate matches our domain
                    if cert_domain == self.domain_name or cert_domain == f"*.{self.domain_name}":
                        # Verify it's still valid
                        cert_details = self.acm.describe_certificate(CertificateArn=cert_arn)
                        status = cert_details['Certificate']['Status']
                        
                        if status == 'ISSUED':
                            logger.info(f"Found valid certificate for {cert_domain}")
                            return cert_arn
            
            return None
        except Exception as e:
            logger.warning(f"Error checking for existing certificates: {e}")
            return None

    async def _request_certificate(self) -> str:
        """Request a new certificate from ACM"""
        validation_method = 'DNS'  # DNS validation is preferred for automation
        
        # Request certificate for the specific domain only
        response = self.acm.request_certificate(
            DomainName=self.domain_name,
            ValidationMethod=validation_method,
            KeyAlgorithm='RSA_2048',  # Use RSA 2048 for compatibility
            Options={
                'CertificateTransparencyLoggingPreference': 'ENABLED'
            },
            Tags=[
                {'Key': 'Name', 'Value': f"{self.project_name}-cert"},
                {'Key': 'Project', 'Value': self.project_name},
                {'Key': 'ManagedBy', 'Value': 'autoform'},
            ]
        )
        
        certificate_arn = response['CertificateArn']
        logger.info(f"Certificate requested: {certificate_arn}")
        
        # Wait a moment for the certificate to be fully created
        time.sleep(2)
        
        return certificate_arn

    async def _get_validation_records(self):
        """Get DNS validation records for the certificate"""
        max_attempts = 10
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = self.acm.describe_certificate(CertificateArn=self.certificate_arn)
                certificate = response['Certificate']
                
                # Extract validation records and deduplicate
                records_map = {}
                for option in certificate.get('DomainValidationOptions', []):
                    if option.get('ValidationMethod') == 'DNS':
                        resource_record = option.get('ResourceRecord', {})
                        if resource_record:
                            # Use Name+Value as key for deduplication
                            record_key = f"{resource_record.get('Name')}||{resource_record.get('Value')}"
                            domain_name = option.get('DomainName')
                            
                            if record_key in records_map:
                                # Add domain to existing record
                                records_map[record_key]['Domains'].append(domain_name)
                            else:
                                # Create new record
                                records_map[record_key] = {
                                    'Name': resource_record.get('Name'),
                                    'Value': resource_record.get('Value'),
                                    'Type': resource_record.get('Type', 'CNAME'),
                                    'Domains': [domain_name],
                                }
                
                self.validation_records = list(records_map.values())
                
                if self.validation_records:
                    logger.info(f"Found {len(self.validation_records)} validation records")
                    return
                
                logger.info(f"Validation records not ready yet, waiting... (attempt {attempt + 1}/{max_attempts})")
                time.sleep(5)
                attempt += 1
                
            except Exception as e:
                logger.error(f"Error getting validation records: {e}")
                time.sleep(5)
                attempt += 1
        
        raise Exception("Failed to get validation records after maximum attempts")

    async def _auto_validate_with_route53(self):
        """Automatically add validation records to Route53"""
        if not self.route53:
            logger.warning("Route53 client not initialized, skipping auto-validation")
            return
        
        # Find the hosted zone for this domain
        hosted_zone_id = await self._find_hosted_zone()
        if not hosted_zone_id:
            logger.warning(f"No Route53 hosted zone found for {self.domain_name}. Manual validation required.")
            return
        
        # Create validation records
        changes = []
        for record in self.validation_records:
            changes.append({
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': record['Name'],
                    'Type': record['Type'],
                    'TTL': 300,
                    'ResourceRecords': [{'Value': record['Value']}]
                }
            })
        
        if changes:
            try:
                response = self.route53.change_resource_record_sets(
                    HostedZoneId=hosted_zone_id,
                    ChangeBatch={
                        'Comment': f'ACM validation for {self.project_name}',
                        'Changes': changes
                    }
                )
                change_id = response['ChangeInfo']['Id']
                logger.info(f"Created Route53 validation records. Change ID: {change_id}")
                
                # Wait for Route53 changes to propagate (with timeout)
                logger.info("Waiting for DNS changes to propagate...")
                waiter = self.route53.get_waiter('resource_record_sets_changed')
                waiter.wait(Id=change_id, WaiterConfig={'Delay': 30, 'MaxAttempts': 20})  # 10 minute timeout
                logger.info("DNS changes propagated successfully")
                
            except Exception as e:
                logger.error(f"Failed to create Route53 validation records: {e}")
                raise

    async def _find_hosted_zone(self) -> Optional[str]:
        """Find Route53 hosted zone for the domain"""
        try:
            # Extract base domain (remove subdomains)
            domain_parts = self.domain_name.split('.')
            
            # Try different domain levels (e.g., app.example.com -> example.com)
            for i in range(len(domain_parts) - 1):
                test_domain = '.'.join(domain_parts[i:])
                
                paginator = self.route53.get_paginator('list_hosted_zones')
                for page in paginator.paginate():
                    for zone in page.get('HostedZones', []):
                        zone_name = zone['Name'].rstrip('.')
                        if zone_name == test_domain:
                            zone_id = zone['Id'].split('/')[-1]
                            logger.info(f"Found hosted zone {zone_name} with ID: {zone_id}")
                            return zone_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding hosted zone: {e}")
            return None

    async def _wait_for_validation(self, timeout_minutes: int = 15):
        """Wait for certificate validation to complete"""
        logger.info(f"Waiting for certificate validation (timeout: {timeout_minutes} minutes)...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while time.time() - start_time < timeout_seconds:
            try:
                response = self.acm.describe_certificate(CertificateArn=self.certificate_arn)
                status = response['Certificate']['Status']
                
                if status == 'ISSUED':
                    logger.info("Certificate validation completed successfully!")
                    return
                elif status == 'FAILED':
                    raise Exception("Certificate validation failed")
                elif status == 'PENDING_VALIDATION':
                    logger.info(f"Certificate still pending validation... (elapsed: {int(time.time() - start_time)}s)")
                
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error checking certificate status: {e}")
                raise
        
        raise Exception(f"Certificate validation timed out after {timeout_minutes} minutes")

    async def get_certificate_status(self) -> str:
        """Get the current status of the certificate"""
        if not self.certificate_arn:
            return "NO_CERTIFICATE"
        
        try:
            response = self.acm.describe_certificate(CertificateArn=self.certificate_arn)
            return response['Certificate']['Status']
        except Exception as e:
            logger.error(f"Error getting certificate status: {e}")
            return "ERROR"
    
    async def get_certificate_validation_records(self) -> Optional[List[dict]]:
        """Get the DNS validation records for the certificate"""
        if not self.certificate_arn:
            return None
        
        try:
            response = self.acm.describe_certificate(CertificateArn=self.certificate_arn)
            certificate = response.get('Certificate', {})
            
            validation_records = []
            for option in certificate.get('DomainValidationOptions', []):
                if option.get('ValidationStatus') == 'PENDING_VALIDATION':
                    record = option.get('ResourceRecord', {})
                    if record:
                        validation_records.append({
                            'Name': record.get('Name', ''),
                            'Type': record.get('Type', 'CNAME'),
                            'Value': record.get('Value', ''),
                            'Domains': [option.get('DomainName', '')]
                        })
            
            return validation_records if validation_records else None
            
        except Exception as e:
            logger.error(f"Error getting certificate validation records: {e}")
            return None
    
    async def create_dns_record_for_load_balancer(self, load_balancer_dns: str) -> bool:
        """Create Route53 A record pointing to the load balancer"""
        if not self.route53:
            logger.warning("Route53 client not initialized, cannot create DNS record")
            return False
        
        # Find the hosted zone
        hosted_zone_id = await self._find_hosted_zone()
        if not hosted_zone_id:
            logger.warning(f"No Route53 hosted zone found for {self.domain_name}. Manual DNS setup required.")
            logger.info(f"Please create a CNAME record: {self.domain_name} -> {load_balancer_dns}")
            return False
        
        try:
            # Create/update the DNS record
            response = self.route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={
                    'Comment': f'Point {self.domain_name} to ALB for {self.project_name}',
                    'Changes': [{
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': self.domain_name,
                            'Type': 'CNAME',
                            'TTL': 300,
                            'ResourceRecords': [{'Value': load_balancer_dns}]
                        }
                    }]
                }
            )
            
            change_id = response['ChangeInfo']['Id']
            logger.info(f"Created DNS record {self.domain_name} -> {load_balancer_dns}")
            logger.info(f"Route53 change ID: {change_id}")
            
            # Wait for DNS changes to propagate (with timeout)
            logger.info("Waiting for DNS changes to propagate...")
            waiter = self.route53.get_waiter('resource_record_sets_changed')
            waiter.wait(Id=change_id, WaiterConfig={'Delay': 30, 'MaxAttempts': 20})  # 10 minute timeout
            logger.info("DNS record created successfully!")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create DNS record: {e}")
            logger.info(f"Please manually create a CNAME record: {self.domain_name} -> {load_balancer_dns}")
            return False
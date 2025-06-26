"""
AWS client utilities with LocalStack support for local development
"""
import os
import boto3
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def is_localstack_enabled() -> bool:
    """Check if LocalStack is enabled via settings"""
    try:
        from core.config import settings
        return settings.use_localstack
    except:
        # Fallback to environment variable
        return os.getenv("USE_LOCALSTACK", "false").lower() == "true"


def get_localstack_endpoint(service: str) -> str:
    """Get LocalStack endpoint for a specific service"""
    try:
        from core.config import settings
        host = settings.localstack_host or "localhost"
        port = settings.localstack_port or 4566
    except:
        # Fallback to environment variables
        host = os.getenv("LOCALSTACK_HOST", "localhost")
        port = int(os.getenv("LOCALSTACK_PORT", "4566"))
    
    # LocalStack uses a single edge port for all services
    return f"http://{host}:{port}"


def get_client_config(
    service: str,
    region: str = None,
    aws_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Get boto3 client configuration with LocalStack support"""
    
    if region is None:
        region = os.getenv("AWS_REGION", "us-east-1")
    
    client_config = {"region_name": region}
    
    # Add credentials if provided
    if aws_credentials:
        client_config.update({
            "aws_access_key_id": aws_credentials.get("access_key"),
            "aws_secret_access_key": aws_credentials.get("secret_key"),
        })
    
    # Configure for LocalStack if enabled
    if is_localstack_enabled():
        endpoint_url = get_localstack_endpoint(service)
        client_config["endpoint_url"] = endpoint_url
        
        # LocalStack doesn't require real credentials, but boto3 does
        # Use dummy credentials if none provided
        if not aws_credentials:
            client_config.update({
                "aws_access_key_id": "test",
                "aws_secret_access_key": "test",
            })
        
        # Disable SSL verification for LocalStack
        client_config["use_ssl"] = False
        client_config["verify"] = False
        
        logger.info(f"Using LocalStack endpoint for {service}: {endpoint_url}")
    
    return client_config


def create_client(
    service: str,
    region: str = None,
    aws_credentials: Optional[Dict[str, str]] = None
):
    """Create a boto3 client with LocalStack support"""
    config = get_client_config(service, region, aws_credentials)
    return boto3.client(service, **config)


def create_resource(
    service: str,
    region: str = None,
    aws_credentials: Optional[Dict[str, str]] = None
):
    """Create a boto3 resource with LocalStack support"""
    config = get_client_config(service, region, aws_credentials)
    return boto3.resource(service, **config)
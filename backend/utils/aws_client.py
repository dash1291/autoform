"""
AWS client utilities with LocalStack support for local development
"""
import os
import boto3
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_client_config(
    service: str,
    region: str = None,
    aws_credentials: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Get boto3 client configuration"""
    
    if region is None:
        region = os.getenv("AWS_REGION", "us-east-1")
    
    client_config = {"region_name": region}
    
    # Add credentials if provided
    if aws_credentials:
        client_config.update({
            "aws_access_key_id": aws_credentials.get("access_key"),
            "aws_secret_access_key": aws_credentials.get("secret_key"),
        })
    
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
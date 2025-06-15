import boto3
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class CloudWatchLogsService:
    """Service for fetching logs from AWS CloudWatch"""
    
    def __init__(self, region_name: str = None, aws_credentials: dict = None):
        if region_name is None:
            region_name = os.getenv('AWS_REGION', 'us-east-1')
        
        self.region_name = region_name
        self.aws_credentials = aws_credentials
        
        try:
            logger.info(f"Initializing AWS clients for region: {region_name}")
            
            # Initialize AWS clients with custom credentials if provided
            client_config = {"region_name": region_name}
            if aws_credentials:
                client_config.update({
                    "aws_access_key_id": aws_credentials["access_key"],
                    "aws_secret_access_key": aws_credentials["secret_key"]
                })
                logger.info("Using custom AWS credentials for CloudWatch service")
            
            # Create session to check credentials
            if aws_credentials:
                session = boto3.Session(
                    aws_access_key_id=aws_credentials["access_key"],
                    aws_secret_access_key=aws_credentials["secret_key"],
                    region_name=region_name
                )
            else:
                session = boto3.Session()
            
            # Get credentials info for debugging (without exposing secrets)
            credentials = session.get_credentials()
            if credentials:
                logger.info(f"AWS credentials found - Access Key ID starts with: {credentials.access_key[:10]}...")
                logger.info(f"Using AWS region: {region_name}")
            else:
                logger.warning("No AWS credentials found!")
            
            self.logs_client = boto3.client('logs', **client_config)
            self.ecs_client = boto3.client('ecs', **client_config)
            
            # Test credentials by making a simple API call
            try:
                sts_client = boto3.client('sts', **client_config)
                identity = sts_client.get_caller_identity()
                logger.info(f"AWS identity confirmed - Account: {identity.get('Account')}, User/Role: {identity.get('Arn', 'unknown')}")
            except Exception as e:
                logger.warning(f"Failed to verify AWS identity: {str(e)}")
            
            logger.info("AWS clients initialized successfully")
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"AWS client initialization failed: {str(e)} - CloudWatch logs will be unavailable")
            self.logs_client = None
            self.ecs_client = None
    
    async def get_project_logs(
        self, 
        project_name: str, 
        limit: int = 100,
        start_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Fetch logs for a project from CloudWatch
        
        Args:
            project_name: Name of the project/ECS service
            limit: Maximum number of log entries to return
            start_time: Start time for log search (defaults to 1 hour ago)
            
        Returns:
            Dictionary containing logs and metadata
        """
        if not self.logs_client:
            return {
                "logs": [],
                "message": "AWS credentials not configured",
                "logGroupName": None,
                "totalStreams": 0
            }
        
        # We'll fetch the most recent logs regardless of age to match UI expectations
        
        log_group_name = f"/ecs/{project_name}"
        
        try:
            # First, check if the log group exists
            logger.info(f"Searching for log group: {log_group_name}")
            try:
                response = self.logs_client.describe_log_groups(
                    logGroupNamePrefix=log_group_name,
                    limit=10  # Get more groups to see what exists
                )
                log_groups = response.get('logGroups', [])
                logger.info(f"Found {len(log_groups)} log groups with prefix {log_group_name}")
                for lg in log_groups:
                    logger.info(f"  - {lg['logGroupName']}")
                
                # Check if our exact log group exists
                exact_match = any(lg['logGroupName'] == log_group_name for lg in log_groups)
                if not exact_match:
                    # List all ECS log groups to help debug
                    all_ecs_response = self.logs_client.describe_log_groups(
                        logGroupNamePrefix="/ecs/",
                        limit=50
                    )
                    all_ecs_groups = [lg['logGroupName'] for lg in all_ecs_response.get('logGroups', [])]
                    logger.info(f"All ECS log groups found: {all_ecs_groups}")
                    
                    return {
                        "logs": [],
                        "message": f"Log group '{log_group_name}' not found. Available ECS log groups: {', '.join(all_ecs_groups) if all_ecs_groups else 'None'}",
                        "logGroupName": log_group_name,
                        "totalStreams": 0
                    }
            except ClientError as e:
                logger.error(f"Error checking log groups: {e.response['Error']['Code']} - {e.response['Error']['Message']}")
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    return {
                        "logs": [],
                        "message": f"No log group found for project '{project_name}'. Make sure the project is deployed and has generated logs.",
                        "logGroupName": log_group_name,
                        "totalStreams": 0
                    }
                raise
            
            # Get log streams for this log group
            streams_response = self.logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy='LastEventTime',
                descending=True,
                limit=10  # Get up to 10 most recent streams
            )
            
            log_streams = streams_response.get('logStreams', [])
            logger.info(f"Found {len(log_streams)} log streams in {log_group_name}")
            
            if not log_streams:
                return {
                    "logs": [],
                    "message": f"No log streams found in log group '{log_group_name}'",
                    "logGroupName": log_group_name,
                    "totalStreams": 0
                }
            
            # Log detailed info about the streams
            for i, stream in enumerate(log_streams[:3]):  # Log first 3 streams
                last_event_time = stream.get('lastEventTime')
                if last_event_time:
                    last_event_dt = datetime.fromtimestamp(last_event_time / 1000)
                    logger.info(f"Stream {i+1}: {stream['logStreamName']}")
                    logger.info(f"  Last event: {last_event_dt} ({last_event_time})")
                    logger.info(f"  First event: {stream.get('firstEventTime', 'unknown')}")
                    logger.info(f"  Stored bytes: {stream.get('storedBytes', 0)}")
                else:
                    logger.info(f"Stream {i+1}: {stream['logStreamName']} - No events")
            
            # Collect log stream names
            stream_names = [stream['logStreamName'] for stream in log_streams]
            
            # Try two approaches: filter_log_events and direct stream reading
            logger.info(f"Fetching last {limit} log events from {log_group_name}")
            
            all_events = []
            
            # Approach 1: Use filter_log_events without time restriction
            try:
                events_response = self.logs_client.filter_log_events(
                    logGroupName=log_group_name,
                    logStreamNames=stream_names,
                    limit=limit * 2
                )
                filter_events = events_response.get('events', [])
                logger.info(f"filter_log_events returned {len(filter_events)} events")
                all_events.extend(filter_events)
            except Exception as e:
                logger.warning(f"filter_log_events failed: {str(e)}")
            
            # Approach 2: If filter_log_events didn't work, try reading from individual streams
            if not all_events and log_streams:
                logger.info("Trying to read from individual log streams...")
                for stream in log_streams[:5]:  # Try first 5 streams
                    try:
                        stream_response = self.logs_client.get_log_events(
                            logGroupName=log_group_name,
                            logStreamName=stream['logStreamName'],
                            startFromHead=False,  # Start from the end (most recent)
                            limit=min(50, limit)  # Get up to 50 events per stream
                        )
                        stream_events = stream_response.get('events', [])
                        logger.info(f"Stream {stream['logStreamName']} returned {len(stream_events)} events")
                        all_events.extend(stream_events)
                        
                        if len(all_events) >= limit:
                            break  # We have enough events
                    except Exception as e:
                        logger.warning(f"Failed to read from stream {stream['logStreamName']}: {str(e)}")
            
            logger.info(f"Total events collected: {len(all_events)}")
            
            # Format the log events for frontend consumption
            logs = []
            for event in all_events:
                logs.append({
                    "timestamp": event['timestamp'],
                    "message": event['message'],
                    "logStreamName": event['logStreamName'],
                    "formattedTime": datetime.fromtimestamp(
                        event['timestamp'] / 1000
                    ).strftime('%Y-%m-%d %H:%M:%S')
                })
            
            # Sort by timestamp (most recent first) and limit to requested amount
            logs.sort(key=lambda x: x['timestamp'], reverse=True)
            logs = logs[:limit]  # Take only the most recent 'limit' entries
            
            return {
                "logs": logs,
                "logGroupName": log_group_name,
                "totalStreams": len(log_streams),
                "message": None if logs else "No log entries found in this log group"
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            logger.error(f"Error fetching CloudWatch logs: {error_code} - {error_message}")
            
            if error_code == 'AccessDeniedException':
                return {
                    "logs": [],
                    "message": "Access denied to CloudWatch logs. Check AWS permissions.",
                    "logGroupName": log_group_name,
                    "totalStreams": 0
                }
            else:
                return {
                    "logs": [],
                    "message": f"Error fetching logs: {error_message}",
                    "logGroupName": log_group_name,
                    "totalStreams": 0
                }
        
        except Exception as e:
            logger.error(f"Unexpected error fetching CloudWatch logs: {str(e)}")
            return {
                "logs": [],
                "message": f"Unexpected error: {str(e)}",
                "logGroupName": log_group_name,
                "totalStreams": 0
            }
    
    async def get_codebuild_logs(self, project_name: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get CodeBuild logs for a project
        
        Args:
            project_name: Name of the project
            limit: Maximum number of log entries to return
            
        Returns:
            Dictionary containing CodeBuild logs and metadata
        """
        if not self.logs_client:
            return {
                "logs": [],
                "message": "AWS credentials not configured",
                "logGroupName": None,
                "totalStreams": 0
            }
        
        # CodeBuild log groups typically follow patterns like:
        # /aws/codebuild/{project-name} or /aws/codebuild/{project-name}-build
        codebuild_patterns = [
            f"/aws/codebuild/{project_name}",
            f"/aws/codebuild/{project_name}-build",
            f"/aws/codebuild/autoform-{project_name}",
            f"/aws/codebuild/autoform-{project_name}-build"
        ]
        
        for pattern in codebuild_patterns:
            try:
                logger.info(f"Searching for CodeBuild log group: {pattern}")
                response = self.logs_client.describe_log_groups(
                    logGroupNamePrefix=pattern,
                    limit=10
                )
                
                log_groups = response.get('logGroups', [])
                if log_groups:
                    log_group_name = log_groups[0]['logGroupName']
                    logger.info(f"Found CodeBuild log group: {log_group_name}")
                    
                    # Get log streams
                    streams_response = self.logs_client.describe_log_streams(
                        logGroupName=log_group_name,
                        orderBy='LastEventTime',
                        descending=True,
                        limit=10
                    )
                    
                    log_streams = streams_response.get('logStreams', [])
                    logger.info(f"Found {len(log_streams)} CodeBuild log streams")
                    
                    if log_streams:
                        # Get events from the most recent streams
                        all_events = []
                        for stream in log_streams[:3]:  # Check first 3 streams
                            try:
                                stream_response = self.logs_client.get_log_events(
                                    logGroupName=log_group_name,
                                    logStreamName=stream['logStreamName'],
                                    startFromHead=False,
                                    limit=min(100, limit)
                                )
                                stream_events = stream_response.get('events', [])
                                all_events.extend(stream_events)
                            except Exception as e:
                                logger.warning(f"Failed to read CodeBuild stream {stream['logStreamName']}: {str(e)}")
                        
                        # Format events
                        logs = []
                        for event in all_events:
                            logs.append({
                                "timestamp": event['timestamp'],
                                "message": event['message'],
                                "logStreamName": event['logStreamName'],
                                "formattedTime": datetime.fromtimestamp(
                                    event['timestamp'] / 1000
                                ).strftime('%Y-%m-%d %H:%M:%S')
                            })
                        
                        # Sort by timestamp (most recent first)
                        logs.sort(key=lambda x: x['timestamp'], reverse=True)
                        logs = logs[:limit]
                        
                        return {
                            "logs": logs,
                            "logGroupName": log_group_name,
                            "totalStreams": len(log_streams),
                            "message": None if logs else "No CodeBuild log entries found"
                        }
            
            except ClientError as e:
                logger.debug(f"CodeBuild log group {pattern} not found: {e.response['Error']['Code']}")
                continue
        
        # If no CodeBuild logs found, list all CodeBuild log groups
        try:
            all_codebuild_response = self.logs_client.describe_log_groups(
                logGroupNamePrefix="/aws/codebuild/",
                limit=50
            )
            all_codebuild_groups = [lg['logGroupName'] for lg in all_codebuild_response.get('logGroups', [])]
            logger.info(f"All CodeBuild log groups: {all_codebuild_groups}")
            
            return {
                "logs": [],
                "message": f"No CodeBuild logs found for project '{project_name}'. Available CodeBuild log groups: {', '.join(all_codebuild_groups) if all_codebuild_groups else 'None'}",
                "logGroupName": None,
                "totalStreams": 0
            }
        except Exception as e:
            return {
                "logs": [],
                "message": f"Error searching for CodeBuild logs: {str(e)}",
                "logGroupName": None,
                "totalStreams": 0
            }

    async def get_log_group_info(self, project_name: str) -> Dict[str, Any]:
        """
        Get information about the log group for a project
        
        Args:
            project_name: Name of the project
            
        Returns:
            Dictionary with log group information
        """
        if not self.logs_client:
            return {"exists": False, "message": "AWS credentials not configured"}
        
        log_group_name = f"/ecs/{project_name}"
        
        try:
            response = self.logs_client.describe_log_groups(
                logGroupNamePrefix=log_group_name,
                limit=1
            )
            
            log_groups = response.get('logGroups', [])
            
            if log_groups:
                log_group = log_groups[0]
                return {
                    "exists": True,
                    "name": log_group['logGroupName'],
                    "creationTime": log_group.get('creationTime'),
                    "retentionInDays": log_group.get('retentionInDays'),
                    "storedBytes": log_group.get('storedBytes', 0)
                }
            else:
                return {
                    "exists": False,
                    "message": f"Log group '{log_group_name}' does not exist"
                }
                
        except ClientError as e:
            logger.error(f"Error checking log group: {str(e)}")
            return {
                "exists": False,
                "message": f"Error checking log group: {e.response['Error']['Message']}"
            }


# Note: The singleton instance is created without credentials.
# For team projects with custom AWS credentials, create a new instance in the router.
cloudwatch_service = CloudWatchLogsService()
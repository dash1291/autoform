"""
Simple test script to check AWS resources fetching
Run this to test if AWS resources can be fetched for your team
"""
import asyncio
import sys
from core.database import prisma
from core.security import get_current_user
from app.routers.aws import get_aws_resources

async def test_aws_resources():
    await prisma.connect()
    
    try:
        # Get teams for testing
        teams = await prisma.team.find_many(include={"awsConfigs": True})
        
        print(f"Found {len(teams)} teams:")
        for team in teams:
            print(f"  Team: {team.name} (ID: {team.id})")
            print(f"    AWS Configs: {len(team.awsConfigs) if team.awsConfigs else 0}")
            
            if team.awsConfigs:
                for config in team.awsConfigs:
                    print(f"      Config: {config.name} - Active: {config.isActive} - Region: {config.awsRegion}")
        
        if teams:
            # Test with first team that has AWS config
            test_team = None
            for team in teams:
                if team.awsConfigs and any(config.isActive for config in team.awsConfigs):
                    test_team = team
                    break
            
            if test_team:
                print(f"\nTesting AWS resources for team: {test_team.name}")
                
                # Create a mock user object
                class MockUser:
                    def __init__(self, user_id):
                        self.id = user_id
                
                # Get team owner
                owner = await prisma.user.find_unique(where={"id": test_team.ownerId})
                if owner:
                    print(f"Team owner: {owner.email}")
                    
                    # Test the endpoint function directly
                    try:
                        import boto3
                        from botocore.exceptions import ClientError, NoCredentialsError
                        from services.encryption_service import encryption_service
                        
                        # Get team AWS config
                        team_aws_config = await prisma.teamawsconfig.find_first(
                            where={"teamId": test_team.id, "isActive": True}
                        )
                        
                        if team_aws_config:
                            print(f"Found active AWS config: {team_aws_config.name}")
                            
                            # Try to decrypt credentials
                            access_key = encryption_service.decrypt(team_aws_config.aws_access_key_id)
                            secret_key = encryption_service.decrypt(team_aws_config.aws_secret_access_key)
                            
                            if access_key and secret_key:
                                print(f"Successfully decrypted credentials")
                                print(f"Access Key: {access_key[:10]}..." if access_key else "None")
                                print(f"Region: {team_aws_config.awsRegion}")
                                
                                # Test AWS connection
                                client_config = {
                                    "region_name": team_aws_config.awsRegion,
                                    "aws_access_key_id": access_key,
                                    "aws_secret_access_key": secret_key,
                                }
                                
                                ec2_client = boto3.client("ec2", **client_config)
                                
                                # Test by listing VPCs
                                vpcs_response = ec2_client.describe_vpcs()
                                print(f"Successfully fetched {len(vpcs_response['Vpcs'])} VPCs")
                                
                                for vpc in vpcs_response['Vpcs'][:3]:  # Show first 3
                                    vpc_name = vpc.get('VpcId')
                                    for tag in vpc.get('Tags', []):
                                        if tag['Key'] == 'Name':
                                            vpc_name = tag['Value']
                                            break
                                    print(f"  VPC: {vpc['VpcId']} ({vpc_name}) - Default: {vpc.get('IsDefault', False)}")
                                
                            else:
                                print("Failed to decrypt AWS credentials")
                        else:
                            print("No active AWS config found for team")
                            
                    except Exception as e:
                        print(f"Error testing AWS connection: {e}")
                else:
                    print("Team owner not found")
            else:
                print("No teams with active AWS configs found")
        else:
            print("No teams found")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await prisma.disconnect()

if __name__ == "__main__":
    asyncio.run(test_aws_resources())
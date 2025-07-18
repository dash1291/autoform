#!/usr/bin/env python3
"""
Script to migrate data from Prisma-style tables to SQLModel tables
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

async def migrate_data():
    """Migrate data from old Prisma tables to new SQLModel tables"""
    
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    print("=== DATA MIGRATION FROM PRISMA TO SQLMODEL ===\n")
    
    try:
        # Start a transaction
        async with conn.transaction():
            
            # 1. Migrate Users (User -> users)
            print("1. Migrating Users...")
            users = await conn.fetch("SELECT * FROM \"User\"")
            if users:
                for user in users:
                    await conn.execute("""
                        INSERT INTO users (id, created_at, updated_at, name, email, email_verified, image, github_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            email = EXCLUDED.email,
                            email_verified = EXCLUDED.email_verified,
                            image = EXCLUDED.image,
                            github_id = EXCLUDED.github_id
                    """, 
                    user['id'], user['createdAt'], user['updatedAt'], user['name'], 
                    user['email'], user['emailVerified'], user['image'], user['githubId'])
                print(f"   Migrated {len(users)} users")
            else:
                print("   No users to migrate")
            
            # 2. Migrate Teams (Team -> teams)
            print("2. Migrating Teams...")
            teams = await conn.fetch("SELECT * FROM \"Team\"")
            if teams:
                for team in teams:
                    await conn.execute("""
                        INSERT INTO teams (id, created_at, updated_at, name, description, owner_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    team['id'], team['createdAt'], team['updatedAt'], team['name'], 
                    team['description'], team['ownerId'])
                print(f"   Migrated {len(teams)} teams")
            else:
                print("   No teams to migrate")
            
            # 3. Migrate TeamMembers (TeamMember -> team_members)
            print("3. Migrating Team Members...")
            team_members = await conn.fetch("SELECT * FROM \"TeamMember\"")
            if team_members:
                for member in team_members:
                    await conn.execute("""
                        INSERT INTO team_members (id, created_at, updated_at, team_id, user_id, role, joined_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    member['id'], member['joinedAt'], member['joinedAt'], member['teamId'], 
                    member['userId'], member['role'], member['joinedAt'])
                print(f"   Migrated {len(team_members)} team members")
            else:
                print("   No team members to migrate")
            
            # 4. Migrate TeamAwsConfigs (TeamAwsConfig -> team_aws_configs)
            print("4. Migrating Team AWS Configs...")
            team_aws_configs = await conn.fetch("SELECT * FROM \"TeamAwsConfig\"")
            if team_aws_configs:
                for config in team_aws_configs:
                    await conn.execute("""
                        INSERT INTO team_aws_configs (id, created_at, updated_at, team_id, name, aws_access_key_id, aws_secret_access_key, aws_region, is_active)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    config['id'], config['createdAt'], config['updatedAt'], config['teamId'], 
                    config['name'], config['awsAccessKeyId'], config['awsSecretAccessKey'], 
                    config['awsRegion'], config['isActive'])
                print(f"   Migrated {len(team_aws_configs)} team AWS configs")
            else:
                print("   No team AWS configs to migrate")
            
            # 5. Migrate Projects (Project -> projects)
            print("5. Migrating Projects...")
            projects = await conn.fetch("SELECT * FROM \"Project\"")
            if projects:
                for project in projects:
                    await conn.execute("""
                        INSERT INTO projects (id, created_at, updated_at, name, git_repo_url, branch, user_id, team_id, status, 
                                            ecs_cluster_arn, ecs_service_arn, alb_arn, domain, existing_vpc_id, existing_subnet_ids, 
                                            existing_cluster_arn, cpu, memory, disk_size, subdirectory, port, health_check_path, 
                                            auto_deploy_enabled, webhook_id, webhook_configured, is_web_service, container_command, secrets_arn)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    project['id'], project['createdAt'], project['updatedAt'], project['name'], 
                    project['gitRepoUrl'], project['branch'], project['userId'], project['teamId'], 
                    project['status'], project['ecsClusterArn'], project['ecsServiceArn'], 
                    project['albArn'], project['domain'], project['existingVpcId'], 
                    project['existingSubnetIds'], project['existingClusterArn'], project['cpu'], 
                    project['memory'], project['diskSize'], project['subdirectory'], project['port'], 
                    project['healthCheckPath'], project['autoDeployEnabled'], project['webhookId'], 
                    project['webhookConfigured'], True, None, project['secretsArn'])
                print(f"   Migrated {len(projects)} projects")
            else:
                print("   No projects to migrate")
            
            # 6. Migrate Environments (Environment -> environments)
            print("6. Migrating Environments...")
            environments = await conn.fetch("SELECT * FROM \"Environment\"")
            if environments:
                for env in environments:
                    await conn.execute("""
                        INSERT INTO environments (id, created_at, updated_at, name, project_id, team_aws_config_id, status, 
                                                branch, cpu, memory, disk_size, existing_vpc_id, existing_subnet_ids, 
                                                existing_cluster_arn, ecs_cluster_arn, ecs_service_arn, alb_arn, alb_name, 
                                                domain, task_definition_arn, secrets_arn)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    env['id'], env['createdAt'], env['updatedAt'], env['name'], 
                    env['projectId'], env['teamAwsConfigId'], env['status'], env['branch'], 
                    env['cpu'], env['memory'], env['diskSize'], env['existingVpcId'], 
                    env['existingSubnetIds'], env['existingClusterArn'], env['ecsClusterArn'], 
                    env['ecsServiceArn'], env['albArn'], env['albName'], env['domain'], 
                    env['taskDefinitionArn'], env['secretsArn'])
                print(f"   Migrated {len(environments)} environments")
            else:
                print("   No environments to migrate")
            
            # 7. Migrate other tables as needed...
            print("7. Migrating other tables...")
            
            # UserAWSConfig
            user_aws_configs = await conn.fetch("SELECT * FROM \"UserAWSConfig\"")
            if user_aws_configs:
                for config in user_aws_configs:
                    await conn.execute("""
                        INSERT INTO user_aws_configs (id, created_at, updated_at, user_id, aws_access_key_id, aws_secret_access_key, aws_region, is_active)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    config['id'], config['createdAt'], config['updatedAt'], config['userId'], 
                    config['awsAccessKeyId'], config['awsSecretAccessKey'], config['awsRegion'], config['isActive'])
                print(f"   Migrated {len(user_aws_configs)} user AWS configs")
            
            # Webhooks
            webhooks = await conn.fetch("SELECT * FROM \"Webhook\"")
            if webhooks:
                for webhook in webhooks:
                    await conn.execute("""
                        INSERT INTO webhooks (id, created_at, updated_at, git_repo_url, secret, is_active)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    webhook['id'], webhook['createdAt'], webhook['updatedAt'], webhook['gitRepoUrl'], 
                    webhook['secret'], webhook['isActive'])
                print(f"   Migrated {len(webhooks)} webhooks")
            
            # Deployments
            deployments = await conn.fetch("SELECT * FROM \"Deployment\"")
            if deployments:
                for deployment in deployments:
                    await conn.execute("""
                        INSERT INTO deployments (id, created_at, updated_at, project_id, environment_id, status, image_tag, commit_sha, logs, details, celery_task_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (id) DO NOTHING
                    """, 
                    deployment['id'], deployment['createdAt'], deployment['updatedAt'], 
                    deployment['projectId'], deployment['environmentId'], deployment['status'], 
                    deployment['imageTag'], deployment['commitSha'], deployment['logs'], 
                    deployment['details'], deployment['celeryTaskId'])
                print(f"   Migrated {len(deployments)} deployments")
            
            print("\n=== MIGRATION COMPLETED SUCCESSFULLY ===")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_data())
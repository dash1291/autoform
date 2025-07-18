#!/usr/bin/env python3
"""
Script to migrate teams and projects data from Prisma to SQLModel tables
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def migrate_teams_projects():
    """Migrate teams and projects data"""
    
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    print("=== MIGRATING TEAMS AND PROJECTS ===\n")
    
    try:
        # 1. Migrate Teams (Team -> teams)
        print("1. Migrating Teams...")
        teams = await conn.fetch("SELECT * FROM \"Team\"")
        if teams:
            for team in teams:
                await conn.execute("""
                    INSERT INTO teams (id, created_at, updated_at, name, description, owner_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        owner_id = EXCLUDED.owner_id
                """, 
                team['id'], team['createdAt'], team['updatedAt'], team['name'], 
                team['description'], team['ownerId'])
            print(f"   Migrated {len(teams)} teams")
        else:
            print("   No teams to migrate")
        
        # 2. Migrate TeamAwsConfigs (TeamAwsConfig -> team_aws_configs)
        print("2. Migrating Team AWS Configs...")
        team_aws_configs = await conn.fetch("SELECT * FROM \"TeamAwsConfig\"")
        if team_aws_configs:
            for config in team_aws_configs:
                await conn.execute("""
                    INSERT INTO team_aws_configs (id, created_at, updated_at, team_id, name, aws_access_key_id, aws_secret_access_key, aws_region, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        aws_access_key_id = EXCLUDED.aws_access_key_id,
                        aws_secret_access_key = EXCLUDED.aws_secret_access_key,
                        aws_region = EXCLUDED.aws_region,
                        is_active = EXCLUDED.is_active
                """, 
                config['id'], config['createdAt'], config['updatedAt'], config['teamId'], 
                config['name'], config['awsAccessKeyId'], config['awsSecretAccessKey'], 
                config['awsRegion'], config['isActive'])
            print(f"   Migrated {len(team_aws_configs)} team AWS configs")
        else:
            print("   No team AWS configs to migrate")
        
        # 3. Migrate Projects (Project -> projects)
        print("3. Migrating Projects...")
        projects = await conn.fetch("SELECT * FROM \"Project\"")
        if projects:
            for project in projects:
                await conn.execute("""
                    INSERT INTO projects (id, created_at, updated_at, name, git_repo_url, branch, user_id, team_id, status, 
                                        ecs_cluster_arn, ecs_service_arn, alb_arn, domain, existing_vpc_id, existing_subnet_ids, 
                                        existing_cluster_arn, cpu, memory, disk_size, subdirectory, port, health_check_path, 
                                        auto_deploy_enabled, webhook_id, webhook_configured, is_web_service, container_command, secrets_arn)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        git_repo_url = EXCLUDED.git_repo_url,
                        branch = EXCLUDED.branch,
                        status = EXCLUDED.status,
                        team_id = EXCLUDED.team_id
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
        
        print("\n=== MIGRATION COMPLETED ===")
        
        # Verify the migration
        print("\nVerifying migration:")
        teams_count = await conn.fetchval("SELECT COUNT(*) FROM teams")
        projects_count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        print(f"Teams in new table: {teams_count}")
        print(f"Projects in new table: {projects_count}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_teams_projects())
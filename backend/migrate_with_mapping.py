#!/usr/bin/env python3
"""
Script to migrate data with proper ID mapping
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def migrate_with_mapping():
    """Migrate data with proper user ID mapping"""
    
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    print("=== MIGRATING WITH USER ID MAPPING ===\n")
    
    try:
        # 1. Find user ID mapping (old -> new)
        print("1. Finding user ID mapping...")
        old_users = await conn.fetch("SELECT * FROM \"User\"")
        new_users = await conn.fetch("SELECT * FROM users")
        
        # Create mapping based on email
        user_mapping = {}
        for old_user in old_users:
            for new_user in new_users:
                if old_user['email'] == new_user['email']:
                    user_mapping[old_user['id']] = new_user['id']
                    print(f"   Mapping: {old_user['id']} -> {new_user['id']} ({old_user['email']})")
        
        if not user_mapping:
            print("   No user mappings found. Cannot proceed.")
            return
        
        # 2. Migrate Teams with mapped owner IDs
        print("2. Migrating Teams...")
        teams = await conn.fetch("SELECT * FROM \"Team\"")
        if teams:
            for team in teams:
                # Map the owner ID
                new_owner_id = user_mapping.get(team['ownerId'])
                if new_owner_id:
                    await conn.execute("""
                        INSERT INTO teams (id, created_at, updated_at, name, description, owner_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            owner_id = EXCLUDED.owner_id
                    """, 
                    team['id'], team['createdAt'], team['updatedAt'], team['name'], 
                    team['description'], new_owner_id)
                    print(f"   Migrated team: {team['name']}")
                else:
                    print(f"   Skipped team {team['name']} - no owner mapping found")
        else:
            print("   No teams to migrate")
        
        # 3. Migrate TeamAwsConfigs
        print("3. Migrating Team AWS Configs...")
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
        
        # 4. Migrate Projects with mapped user IDs
        print("4. Migrating Projects...")
        projects = await conn.fetch("SELECT * FROM \"Project\"")
        if projects:
            for project in projects:
                # Map the user ID
                new_user_id = user_mapping.get(project['userId'])
                if new_user_id:
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
                    project['gitRepoUrl'], project['branch'], new_user_id, project['teamId'], 
                    project['status'], project['ecsClusterArn'], project['ecsServiceArn'], 
                    project['albArn'], project['domain'], project['existingVpcId'], 
                    project['existingSubnetIds'], project['existingClusterArn'], project['cpu'], 
                    project['memory'], project['diskSize'], project['subdirectory'], project['port'], 
                    project['healthCheckPath'], project['autoDeployEnabled'], None, # Set webhook_id to NULL
                    project['webhookConfigured'], True, None, project['secretsArn'])
                    print(f"   Migrated project: {project['name']}")
                else:
                    print(f"   Skipped project {project['name']} - no user mapping found")
        else:
            print("   No projects to migrate")
        
        print("\n=== MIGRATION COMPLETED ===")
        
        # Verify the migration
        print("\nVerifying migration:")
        teams_count = await conn.fetchval("SELECT COUNT(*) FROM teams")
        projects_count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        print(f"Teams in new table: {teams_count}")
        print(f"Projects in new table: {projects_count}")
        
        # Show the migrated data
        print("\nMigrated teams:")
        teams_new = await conn.fetch("SELECT name, owner_id FROM teams")
        for team in teams_new:
            print(f"  - {team['name']} (Owner: {team['owner_id']})")
        
        print("\nMigrated projects:")
        projects_new = await conn.fetch("SELECT name, user_id, team_id FROM projects")
        for project in projects_new:
            print(f"  - {project['name']} (User: {project['user_id']}, Team: {project['team_id']})")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_with_mapping())
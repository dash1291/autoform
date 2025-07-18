#!/usr/bin/env python3
"""
Script to migrate environment-related data from Prisma to SQLModel tables
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def migrate_environments():
    """Migrate environment-related data"""
    
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    print("=== MIGRATING ENVIRONMENT DATA ===\n")
    
    try:
        # 1. Migrate Environments (Environment -> environments)
        print("1. Migrating Environments...")
        environments = await conn.fetch("SELECT * FROM \"Environment\"")
        if environments:
            for env in environments:
                await conn.execute("""
                    INSERT INTO environments (id, created_at, updated_at, name, project_id, team_aws_config_id, status, 
                                            branch, cpu, memory, disk_size, existing_vpc_id, existing_subnet_ids, 
                                            existing_cluster_arn, ecs_cluster_arn, ecs_service_arn, alb_arn, alb_name, 
                                            domain, task_definition_arn, secrets_arn)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        branch = EXCLUDED.branch,
                        cpu = EXCLUDED.cpu,
                        memory = EXCLUDED.memory,
                        disk_size = EXCLUDED.disk_size,
                        existing_vpc_id = EXCLUDED.existing_vpc_id,
                        existing_subnet_ids = EXCLUDED.existing_subnet_ids,
                        existing_cluster_arn = EXCLUDED.existing_cluster_arn,
                        ecs_cluster_arn = EXCLUDED.ecs_cluster_arn,
                        ecs_service_arn = EXCLUDED.ecs_service_arn,
                        alb_arn = EXCLUDED.alb_arn,
                        alb_name = EXCLUDED.alb_name,
                        domain = EXCLUDED.domain,
                        task_definition_arn = EXCLUDED.task_definition_arn,
                        secrets_arn = EXCLUDED.secrets_arn
                """, 
                env['id'], env['createdAt'], env['updatedAt'], env['name'], 
                env['projectId'], env['teamAwsConfigId'], env['status'], env['branch'], 
                env['cpu'], env['memory'], env['diskSize'], env['existingVpcId'], 
                env['existingSubnetIds'], env['existingClusterArn'], env['ecsClusterArn'], 
                env['ecsServiceArn'], env['albArn'], env['albName'], env['domain'], 
                env['taskDefinitionArn'], env['secretsArn'])
                print(f"   Migrated environment: {env['name']} (Project: {env['projectId']})")
            print(f"   Total migrated: {len(environments)} environments")
        else:
            print("   No environments to migrate")
        
        # 2. Migrate Environment Variables (EnvironmentVariable -> environment_variables)
        print("\\n2. Migrating Environment Variables...")
        env_vars = await conn.fetch("SELECT * FROM \"EnvironmentVariable\"")
        if env_vars:
            for var in env_vars:
                await conn.execute("""
                    INSERT INTO environment_variables (id, created_at, updated_at, environment_id, project_id, key, value, is_secret, secret_key)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO UPDATE SET
                        key = EXCLUDED.key,
                        value = EXCLUDED.value,
                        is_secret = EXCLUDED.is_secret,
                        secret_key = EXCLUDED.secret_key
                """, 
                var['id'], var['createdAt'], var['updatedAt'], var['environmentId'], 
                var['projectId'], var['key'], var['value'], var['isSecret'], var['secretKey'])
                secret_indicator = " (SECRET)" if var['isSecret'] else ""
                print(f"   Migrated: {var['key']}{secret_indicator} (Env: {var['environmentId']})")
            print(f"   Total migrated: {len(env_vars)} environment variables")
        else:
            print("   No environment variables to migrate")
        
        # 3. Migrate Deployments (Deployment -> deployments)
        print("\\n3. Migrating Deployments...")
        deployments = await conn.fetch("SELECT * FROM \"Deployment\"")
        if deployments:
            for deploy in deployments:
                await conn.execute("""
                    INSERT INTO deployments (id, created_at, updated_at, project_id, environment_id, status, image_tag, commit_sha, logs, details, celery_task_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        image_tag = EXCLUDED.image_tag,
                        commit_sha = EXCLUDED.commit_sha,
                        logs = EXCLUDED.logs,
                        details = EXCLUDED.details,
                        celery_task_id = EXCLUDED.celery_task_id
                """, 
                deploy['id'], deploy['createdAt'], deploy['updatedAt'], 
                deploy['projectId'], deploy['environmentId'], deploy['status'], 
                deploy['imageTag'], deploy['commitSha'], deploy['logs'], 
                deploy['details'], deploy['celeryTaskId'])
                print(f"   Migrated deployment: {deploy['id']} - {deploy['status']} (Project: {deploy['projectId']})")
            print(f"   Total migrated: {len(deployments)} deployments")
        else:
            print("   No deployments to migrate")
        
        print("\\n=== MIGRATION COMPLETED ===")
        
        # Verify the migration
        print("\\nVerifying migration:")
        environments_count = await conn.fetchval("SELECT COUNT(*) FROM environments")
        env_vars_count = await conn.fetchval("SELECT COUNT(*) FROM environment_variables")
        deployments_count = await conn.fetchval("SELECT COUNT(*) FROM deployments")
        
        print(f"Environments: {environments_count}")
        print(f"Environment Variables: {env_vars_count}")
        print(f"Deployments: {deployments_count}")
        
        # Show migrated environments with their variables
        print("\\nMigrated environments with variables:")
        envs_with_vars = await conn.fetch("""
            SELECT e.name as env_name, e.project_id, COUNT(ev.id) as var_count
            FROM environments e
            LEFT JOIN environment_variables ev ON e.id = ev.environment_id
            GROUP BY e.id, e.name, e.project_id
            ORDER BY e.name
        """)
        for env in envs_with_vars:
            print(f"  - {env['env_name']} (Project: {env['project_id']}) - {env['var_count']} variables")
        
        # Show secret vs non-secret variables
        print("\\nEnvironment variables breakdown:")
        secret_count = await conn.fetchval("SELECT COUNT(*) FROM environment_variables WHERE is_secret = true")
        non_secret_count = await conn.fetchval("SELECT COUNT(*) FROM environment_variables WHERE is_secret = false")
        print(f"  - Secret variables: {secret_count}")
        print(f"  - Non-secret variables: {non_secret_count}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_environments())
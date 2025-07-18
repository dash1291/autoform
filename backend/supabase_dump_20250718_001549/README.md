# Supabase Database Dump

This directory contains a complete dump of all application tables from the Supabase database.

## Generated on
- **Date**: 2025-07-18 00:15:51 UTC
- **Database**: autoform
- **Type**: Data-only dump (structure not included)

## Tables Dumped

| Table Name | Records | Status | Description |
|------------|---------|--------|-------------|
| users | 1 | ✓ | User accounts |
| accounts | 1 | ✓ | OAuth account links |
| sessions | 0 | ⚠ Empty | User sessions |
| verification_tokens | 0 | ⚠ Empty | Email verification tokens |
| user_aws_configs | 0 | ⚠ Empty | Personal AWS configurations |
| teams | 1 | ✓ | Team organizations |
| team_members | 0 | ⚠ Empty | Team memberships |
| team_aws_configs | 2 | ✓ | Team AWS configurations |
| projects | 2 | ✓ | Projects |
| environments | 2 | ✓ | Deployment environments |
| environment_variables | 14 | ✓ | Environment variables |
| deployments | 43 | ✓ | Deployment history |
| webhooks | 1 | ✓ | GitHub webhooks |

## Files Included

### Data Files (JSON)
- `*_data.json` - Individual table data in JSON format
- `dump_summary.json` - Summary of the dump process

### SQL Files  
- `database_dump.sql` - Complete SQL dump for restoration
- `restore_database.sh` - Shell script to restore the database

## How to Use

### Option 1: Restore using SQL dump (Recommended)
```bash
# Make sure you have psql installed
# Set your database URL
export DATABASE_URL="postgresql://user:password@host:port/database"

# Run the restore script
./restore_database.sh
```

### Option 2: Restore using psql directly
```bash
psql "$DATABASE_URL" < database_dump.sql
```

### Option 3: Use individual JSON files
Each table's data is available in JSON format for custom processing.

## Important Notes

⚠️ **WARNING**: This restore will **DELETE ALL EXISTING DATA** in the target database before importing the dump.

🔒 **SECURITY**: This dump may contain sensitive information including:
- Encrypted AWS credentials
- User information
- Environment variables
- Deployment logs

Make sure to:
1. Store this dump securely
2. Only restore to development/staging environments
3. Verify the target database before restoration
4. Consider sanitizing sensitive data for non-production use

## Database Schema

The dump includes data for the following application components:
- **Authentication**: Users, accounts, sessions, verification tokens
- **Teams**: Team management and AWS configurations
- **Projects**: Project definitions and configurations
- **Environments**: Deployment environments and variables
- **Deployments**: Deployment history and logs
- **Webhooks**: GitHub webhook configurations

## Troubleshooting

If restoration fails:
1. Check database connection parameters
2. Ensure target database exists
3. Verify user has sufficient permissions
4. Check PostgreSQL logs for detailed error messages

## Scripts Used

The dump was created using:
- `quick_dump.py` - Main dump script
- `create_sql_dump.py` - SQL conversion script

Total records dumped: **66 records** across **13 tables**
#!/usr/bin/env python3
"""
Create SQL dump from the JSON data files
"""

import os
import json
import sys
from datetime import datetime

def json_to_sql_value(value):
    """Convert a JSON value to SQL format"""
    if value is None:
        return "NULL"
    elif isinstance(value, str):
        # Escape single quotes and wrap in quotes
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        # For other types, convert to string and quote
        return f"'{str(value)}'"

def create_sql_dump(dump_dir):
    """Create SQL dump from JSON files"""
    
    # Tables in dependency order (to respect foreign key constraints)
    tables_order = [
        "users",
        "accounts",
        "sessions", 
        "verification_tokens",
        "user_aws_configs",
        "teams",
        "team_members",
        "team_aws_configs",
        "projects",
        "environments",
        "environment_variables",
        "deployments",
        "webhooks"
    ]
    
    sql_lines = []
    
    # Add header
    sql_lines.append("-- Supabase Database Dump")
    sql_lines.append(f"-- Generated on: {datetime.now().isoformat()}")
    sql_lines.append("-- Database: autoform")
    sql_lines.append("-- Generated from JSON dump files")
    sql_lines.append("")
    sql_lines.append("-- Disable foreign key checks during import")
    sql_lines.append("SET session_replication_role = 'replica';")
    sql_lines.append("")
    
    for table_name in tables_order:
        json_file = f"{dump_dir}/{table_name}_data.json"
        
        if not os.path.exists(json_file):
            sql_lines.append(f"-- No data file found for {table_name}")
            sql_lines.append("")
            continue
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            if not data:
                sql_lines.append(f"-- Table {table_name} is empty")
                sql_lines.append("")
                continue
            
            sql_lines.append(f"-- Data for table: {table_name}")
            sql_lines.append(f"DELETE FROM {table_name};")
            
            for row in data:
                if not row:  # Skip empty rows
                    continue
                
                columns = list(row.keys())
                values = [json_to_sql_value(row[col]) for col in columns]
                
                columns_str = ", ".join(columns)
                values_str = ", ".join(values)
                sql_lines.append(f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str});")
            
            sql_lines.append("")
            print(f"✓ Processed {len(data)} rows from {table_name}")
            
        except Exception as e:
            sql_lines.append(f"-- Error processing {table_name}: {e}")
            sql_lines.append("")
            print(f"✗ Error processing {table_name}: {e}")
    
    # Re-enable foreign key checks
    sql_lines.append("-- Re-enable foreign key checks")
    sql_lines.append("SET session_replication_role = 'origin';")
    sql_lines.append("")
    sql_lines.append("-- End of dump")
    
    # Save SQL dump
    sql_file = f"{dump_dir}/database_dump.sql"
    with open(sql_file, "w") as f:
        f.write("\\n".join(sql_lines))
    
    print(f"✓ Created SQL dump: {sql_file}")

def create_restore_script(dump_dir):
    """Create a restore script"""
    restore_script = f"""#!/bin/bash
# Database Restore Script
# Restores the database from the SQL dump

# Set your database connection parameters
DATABASE_URL="${{DATABASE_URL:-postgresql://postgres:password@localhost:5432/autoform}}"

echo "Starting database restore..."
echo "Database URL: $DATABASE_URL"

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "Error: psql is not installed or not in PATH"
    exit 1
fi

# Check if dump file exists
if [ ! -f "database_dump.sql" ]; then
    echo "Error: database_dump.sql not found"
    exit 1
fi

# Restore the database
echo "Restoring database from database_dump.sql..."
psql "$DATABASE_URL" < database_dump.sql

if [ $? -eq 0 ]; then
    echo "✓ Database restore completed successfully!"
else
    echo "✗ Database restore failed!"
    exit 1
fi
"""
    
    restore_file = f"{dump_dir}/restore_database.sh"
    with open(restore_file, "w") as f:
        f.write(restore_script)
    
    # Make it executable
    os.chmod(restore_file, 0o755)
    print(f"✓ Created restore script: {restore_file}")

def main():
    if len(sys.argv) != 2:
        print("Usage: python create_sql_dump.py <dump_directory>")
        sys.exit(1)
    
    dump_dir = sys.argv[1]
    
    if not os.path.exists(dump_dir):
        print(f"Error: Directory {dump_dir} does not exist")
        sys.exit(1)
    
    print(f"Creating SQL dump from JSON files in: {dump_dir}")
    
    create_sql_dump(dump_dir)
    create_restore_script(dump_dir)
    
    print("\\n🎉 SQL dump creation completed!")
    print(f"📄 SQL dump: {dump_dir}/database_dump.sql")
    print(f"🔧 Restore script: {dump_dir}/restore_database.sh")

if __name__ == "__main__":
    main()
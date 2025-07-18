#!/usr/bin/env python3
"""
Supabase Database Dump Script
Creates a comprehensive dump of all application tables from Supabase
"""

import os
import json
import asyncio
from datetime import datetime
from sqlmodel import select, create_engine, Session
from sqlalchemy import text, inspect
import asyncpg

# Import all models
from models.user import User, Account, Session as UserSession, VerificationToken, UserAwsConfig
from models.team import Team, TeamMember, TeamAwsConfig
from models.project import Project
from models.environment import Environment, EnvironmentVariable
from models.deployment import Deployment
from models.webhook import Webhook

# Database connection parameters
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/autoform")

# All tables in the application
TABLES = [
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

def create_dump_directory():
    """Create a directory for the dump files"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_dir = f"supabase_dump_{timestamp}"
    os.makedirs(dump_dir, exist_ok=True)
    return dump_dir

def dump_table_structure(engine, table_name, dump_dir):
    """Dump the structure of a table"""
    with engine.connect() as conn:
        # Get table schema
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        indexes = inspector.get_indexes(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)
        primary_key = inspector.get_pk_constraint(table_name)
        
        structure = {
            "table_name": table_name,
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "primary_key": primary_key
        }
        
        # Save structure to file
        with open(f"{dump_dir}/{table_name}_structure.json", "w") as f:
            json.dump(structure, f, indent=2, default=str)
        
        print(f"✓ Dumped structure for {table_name}")

def dump_table_data(engine, table_name, dump_dir):
    """Dump the data of a table"""
    try:
        with engine.connect() as conn:
            # Get row count
            count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = count_result.scalar()
            
            if row_count == 0:
                print(f"⚠ Table {table_name} is empty")
                return
            
            # Get all data
            result = conn.execute(text(f"SELECT * FROM {table_name}"))
            rows = result.fetchall()
            columns = result.keys()
            
            # Convert to list of dictionaries
            data = []
            for row in rows:
                row_dict = {}
                for i, column in enumerate(columns):
                    value = row[i]
                    # Handle datetime and other non-serializable types
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    row_dict[column] = value
                data.append(row_dict)
            
            # Save data to file
            with open(f"{dump_dir}/{table_name}_data.json", "w") as f:
                json.dump(data, f, indent=2, default=str)
            
            print(f"✓ Dumped {row_count} rows from {table_name}")
            
    except Exception as e:
        print(f"✗ Error dumping {table_name}: {e}")

def create_restore_script(dump_dir):
    """Create a script to restore the database"""
    restore_script = f"""#!/usr/bin/env python3
'''
Database Restore Script
Restores the database from the dump files in {dump_dir}
'''

import os
import json
import sys
from sqlmodel import create_engine, Session, text

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/autoform")

def restore_database():
    engine = create_engine(DATABASE_URL)
    
    # Tables to restore in order (respecting foreign key constraints)
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
    
    with Session(engine) as session:
        for table in tables_order:
            try:
                # Load data
                with open(f"{table}_data.json", "r") as f:
                    data = json.load(f)
                
                if not data:
                    print(f"⚠ No data to restore for {{table}}")
                    continue
                
                # Clear existing data
                session.execute(text(f"DELETE FROM {{table}}"))
                
                # Insert data
                for row in data:
                    columns = ", ".join(row.keys())
                    values = ", ".join([f":%s" % k for k in row.keys()])
                    query = f"INSERT INTO {{table}} ({{columns}}) VALUES ({{values}})"
                    session.execute(text(query), row)
                
                session.commit()
                print(f"✓ Restored {{len(data)}} rows to {{table}}")
                
            except Exception as e:
                print(f"✗ Error restoring {{table}}: {{e}}")
                session.rollback()

if __name__ == "__main__":
    print("Starting database restore...")
    restore_database()
    print("Database restore completed!")
"""
    
    with open(f"{dump_dir}/restore_database.py", "w") as f:
        f.write(restore_script)
    
    # Make it executable
    os.chmod(f"{dump_dir}/restore_database.py", 0o755)
    print(f"✓ Created restore script: {dump_dir}/restore_database.py")

def create_sql_dump(engine, dump_dir):
    """Create a SQL dump file"""
    sql_dump = []
    
    # Add header
    sql_dump.append("-- Supabase Database Dump")
    sql_dump.append(f"-- Generated on: {datetime.now().isoformat()}")
    sql_dump.append("-- Database: autoform")
    sql_dump.append("")
    
    for table_name in TABLES:
        try:
            with engine.connect() as conn:
                # Get table data
                result = conn.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()
                columns = result.keys()
                
                if not rows:
                    sql_dump.append(f"-- Table {table_name} is empty")
                    sql_dump.append("")
                    continue
                
                sql_dump.append(f"-- Data for table: {table_name}")
                sql_dump.append(f"DELETE FROM {table_name};")
                
                for row in rows:
                    values = []
                    for value in row:
                        if value is None:
                            values.append("NULL")
                        elif isinstance(value, str):
                            # Escape single quotes
                            escaped = value.replace("'", "''")
                            values.append(f"'{escaped}'")
                        elif isinstance(value, (int, float)):
                            values.append(str(value))
                        else:
                            values.append(f"'{str(value)}'")
                    
                    columns_str = ", ".join(columns)
                    values_str = ", ".join(values)
                    sql_dump.append(f"INSERT INTO {table_name} ({columns_str}) VALUES ({values_str});")
                
                sql_dump.append("")
                
        except Exception as e:
            sql_dump.append(f"-- Error dumping {table_name}: {e}")
            sql_dump.append("")
    
    # Save SQL dump
    with open(f"{dump_dir}/database_dump.sql", "w") as f:
        f.write("\\n".join(sql_dump))
    
    print(f"✓ Created SQL dump: {dump_dir}/database_dump.sql")

def main():
    print("Starting Supabase database dump...")
    print(f"Database URL: {DATABASE_URL}")
    
    # Create dump directory
    dump_dir = create_dump_directory()
    print(f"Dump directory: {dump_dir}")
    
    # Create database engine
    engine = create_engine(DATABASE_URL)
    
    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return
    
    # Dump each table
    for table_name in TABLES:
        print(f"\\nProcessing table: {table_name}")
        dump_table_structure(engine, table_name, dump_dir)
        dump_table_data(engine, table_name, dump_dir)
    
    # Create restore script
    create_restore_script(dump_dir)
    
    # Create SQL dump
    create_sql_dump(engine, dump_dir)
    
    # Create summary
    summary = {
        "dump_created": datetime.now().isoformat(),
        "database_url": DATABASE_URL,
        "tables_dumped": TABLES,
        "dump_directory": dump_dir
    }
    
    with open(f"{dump_dir}/dump_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\\n🎉 Database dump completed successfully!")
    print(f"📁 Files created in: {dump_dir}")
    print(f"📄 Summary: {dump_dir}/dump_summary.json")
    print(f"🔧 Restore script: {dump_dir}/restore_database.py")
    print(f"💾 SQL dump: {dump_dir}/database_dump.sql")

if __name__ == "__main__":
    main()
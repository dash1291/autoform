#!/usr/bin/env python3
"""
Quick Database Dump Script
Uses the existing database connection from the app
"""

import os
import json
import asyncio
from datetime import datetime
from core.database import get_async_session
from sqlmodel import select, text

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

async def dump_table_data(table_name, dump_dir):
    """Dump the data of a table"""
    try:
        async with get_async_session() as session:
            # Get row count
            count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = count_result.scalar()
            
            if row_count == 0:
                print(f"⚠ Table {table_name} is empty")
                with open(f"{dump_dir}/{table_name}_data.json", "w") as f:
                    json.dump([], f, indent=2)
                return
            
            # Get all data
            result = await session.execute(text(f"SELECT * FROM {table_name}"))
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
                    elif isinstance(value, bytes):
                        # Handle binary data
                        value = value.hex()
                    row_dict[column] = value
                data.append(row_dict)
            
            # Save data to file
            with open(f"{dump_dir}/{table_name}_data.json", "w") as f:
                json.dump(data, f, indent=2, default=str)
            
            print(f"✓ Dumped {row_count} rows from {table_name}")
            
    except Exception as e:
        print(f"✗ Error dumping {table_name}: {e}")
        # Create empty file for failed tables
        with open(f"{dump_dir}/{table_name}_data.json", "w") as f:
            json.dump([], f, indent=2)

async def main():
    print("Starting quick database dump...")
    
    # Create dump directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_dir = f"supabase_dump_{timestamp}"
    os.makedirs(dump_dir, exist_ok=True)
    print(f"Dump directory: {dump_dir}")
    
    # Test connection
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return
    
    # Dump each table
    for table_name in TABLES:
        print(f"Processing table: {table_name}")
        await dump_table_data(table_name, dump_dir)
    
    # Create summary
    summary = {
        "dump_created": datetime.now().isoformat(),
        "tables_dumped": TABLES,
        "dump_directory": dump_dir,
        "note": "This is a data-only dump. Structure information not included."
    }
    
    with open(f"{dump_dir}/dump_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\\n🎉 Database dump completed successfully!")
    print(f"📁 Files created in: {dump_dir}")
    print(f"📄 Summary: {dump_dir}/dump_summary.json")

if __name__ == "__main__":
    asyncio.run(main())
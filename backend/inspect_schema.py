#!/usr/bin/env python3
"""
Script to inspect the existing database schema and compare with SQLModel expectations
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

async def inspect_database():
    """Inspect the current database schema"""
    
    # Connect to database
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    print("=== DATABASE SCHEMA INSPECTION ===\n")
    
    try:
        # 1. List all tables
        print("1. EXISTING TABLES:")
        tables = await conn.fetch("""
            SELECT tablename, schemaname 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename;
        """)
        
        for table in tables:
            print(f"   - {table['tablename']}")
        
        if not tables:
            print("   No tables found in public schema")
            return
        
        print("\n" + "="*50 + "\n")
        
        # 2. Inspect each table structure
        for table in tables:
            table_name = table['tablename']
            print(f"2. TABLE: {table_name}")
            
            # Get column information
            columns = await conn.fetch(f"""
                SELECT 
                    column_name, 
                    data_type, 
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND table_schema = 'public'
                ORDER BY ordinal_position;
            """)
            
            print("   Columns:")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                print(f"   - {col['column_name']}: {col['data_type']}{max_len} {nullable}{default}")
            
            # Get sample data count
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                print(f"   Records: {count}")
            except Exception as e:
                print(f"   Records: Error counting - {e}")
            
            # Show sample data for key tables
            if table_name in ['teams', 'users', 'projects', 'environments'] and count > 0:
                try:
                    sample = await conn.fetch(f"SELECT * FROM {table_name} LIMIT 2")
                    print("   Sample data:")
                    for row in sample:
                        print(f"   - {dict(row)}")
                except Exception as e:
                    print(f"   Sample data: Error - {e}")
            
            print("\n" + "-"*30 + "\n")
        
        # 3. Check foreign key relationships
        print("3. FOREIGN KEY RELATIONSHIPS:")
        fkeys = await conn.fetch("""
            SELECT 
                tc.constraint_name,
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM information_schema.table_constraints AS tc 
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public';
        """)
        
        if fkeys:
            for fk in fkeys:
                print(f"   - {fk['table_name']}.{fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}")
        else:
            print("   No foreign key relationships found")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect_database())
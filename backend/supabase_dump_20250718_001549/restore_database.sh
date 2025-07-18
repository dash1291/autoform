#!/bin/bash
# Database Restore Script
# Restores the database from the SQL dump

# Set your database connection parameters
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:password@localhost:5432/autoform}"

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

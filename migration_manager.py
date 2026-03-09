#!/usr/bin/env python3
"""
Deterministic Migration Manager for Mayasec Database

Requirements:
- Idempotent: Safe to run multiple times
- Versioned: Track applied migrations
- Order-independent: Dependencies explicit in SQL
- No ORM: Raw SQL migrations for transparency
- Rollback-aware: Track state for debugging

Architecture:
1. Scan migrations/ directory for numbered .sql files
2. Check schema_migrations table for applied versions
3. Execute missing migrations in order
4. Track success/failure with timestamps
"""

import os
import sys
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MigrationManager')


class MigrationManager:
    """Manages deterministic database migrations"""
    
    def __init__(self, db_host: str, db_port: int, db_name: str, db_user: str, db_password: str):
        """Initialize migration manager with DB connection parameters"""
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        migrations_dir = os.getenv('MAYASEC_MIGRATIONS_DIR')
        self.migrations_dir = Path(migrations_dir) if migrations_dir else Path(__file__).parent / 'migrations'
        self.conn = None
        
    def connect(self) -> bool:
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            logger.info(f"Connected to database: {self.db_name}@{self.db_host}:{self.db_port}")
            return True
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from database")
    
    def _ensure_migrations_table(self):
        """Create schema_migrations table if it doesn't exist"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(50) PRIMARY KEY,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'success',
                    error_message TEXT
                )
            ''')
            self.conn.commit()
            cursor.close()
            logger.info("schema_migrations table verified")
        except psycopg2.Error as e:
            logger.error(f"Failed to create schema_migrations table: {e}")
            raise
    
    def get_applied_migrations(self) -> Dict[str, Dict[str, Any]]:
        """Get all applied migrations from schema_migrations table"""
        applied = {}
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM schema_migrations ORDER BY version')
            for row in cursor.fetchall():
                applied[row['version']] = dict(row)
            cursor.close()
        except psycopg2.Error as e:
            logger.warning(f"Could not read applied migrations: {e}")
        return applied
    
    def get_pending_migrations(self) -> List[tuple]:
        """
        Get migrations that need to be applied
        
        Returns: List of (version, filepath) tuples in order
        """
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return []
        
        # Find all .sql files in migrations directory
        migration_files = sorted(self.migrations_dir.glob('*.sql'))
        applied = self.get_applied_migrations()
        pending = []
        
        for filepath in migration_files:
            version = filepath.stem  # e.g., "001_create_events"
            if version not in applied:
                pending.append((version, filepath))
        
        return pending
    
    def execute_migration(self, version: str, filepath: Path) -> bool:
        """
        Execute a single migration file
        
        Migration is executed in a transaction. If it fails, it's rolled back
        and recorded in schema_migrations with error details.
        """
        try:
            cursor = self.conn.cursor()
            
            # Read migration file
            with open(filepath, 'r') as f:
                sql = f.read()
            
            if not sql.strip():
                logger.warning(f"Migration {version} is empty, skipping")
                return True
            
            logger.info(f"Executing migration: {version}")
            
            # Execute migration
            cursor.execute(sql)
            self.conn.commit()
            
            # Record in schema_migrations
            cursor.execute('''
                INSERT INTO schema_migrations (version, description, status)
                VALUES (%s, %s, %s)
            ''', (version, f"Migration {version}", 'success'))
            self.conn.commit()
            
            cursor.close()
            logger.info(f"✓ Migration completed: {version}")
            return True
            
        except psycopg2.Error as e:
            error_msg = str(e)
            logger.error(f"✗ Migration failed: {version}")
            logger.error(f"  Error: {error_msg}")
            
            try:
                self.conn.rollback()
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO schema_migrations (version, description, status, error_message)
                    VALUES (%s, %s, %s, %s)
                ''', (version, f"Migration {version}", 'failed', error_msg))
                self.conn.commit()
                cursor.close()
            except Exception as inner_e:
                logger.error(f"Could not record migration failure: {inner_e}")
            
            return False
    
    def run(self) -> bool:
        """
        Run all pending migrations
        
        Returns: True if all migrations succeeded, False if any failed
        """
        try:
            if not self.connect():
                return False
            
            self._ensure_migrations_table()
            pending = self.get_pending_migrations()
            
            if not pending:
                logger.info("No pending migrations")
                return True
            
            logger.info(f"Found {len(pending)} pending migration(s)")
            
            all_succeeded = True
            for version, filepath in pending:
                if not self.execute_migration(version, filepath):
                    all_succeeded = False
                    # Continue with remaining migrations to see all errors
            
            if all_succeeded:
                logger.info("✓ All migrations completed successfully")
            else:
                logger.error("✗ Some migrations failed")
            
            return all_succeeded
            
        finally:
            self.disconnect()
    
    def status(self) -> bool:
        """Show migration status and history"""
        try:
            if not self.connect():
                return False
            
            self._ensure_migrations_table()
            applied = self.get_applied_migrations()
            pending = self.get_pending_migrations()
            
            print("\n=== Migration Status ===")
            
            if applied:
                print("\nApplied Migrations:")
                for version, info in applied.items():
                    status = info.get('status', 'unknown')
                    applied_at = info.get('applied_at', 'unknown')
                    status_symbol = "✓" if status == 'success' else "✗"
                    print(f"  {status_symbol} {version} ({applied_at})")
                    if status == 'failed' and info.get('error_message'):
                        print(f"    Error: {info['error_message']}")
            else:
                print("\nNo migrations applied yet")
            
            if pending:
                print(f"\nPending Migrations ({len(pending)}):")
                for version, filepath in pending:
                    print(f"  - {version}")
            else:
                print("\nNo pending migrations")
            
            print()
            return True
            
        finally:
            self.disconnect()


def main():
    """CLI for migration manager"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Mayasec Database Migration Manager')
    parser.add_argument('command', choices=['run', 'status'], help='Command to execute')
    parser.add_argument('--host', default=os.getenv('DB_HOST', 'localhost'), help='Database host')
    parser.add_argument('--port', type=int, default=int(os.getenv('DB_PORT', 5432)), help='Database port')
    parser.add_argument('--name', default=os.getenv('DB_NAME', 'mayasec'), help='Database name')
    parser.add_argument('--user', default=os.getenv('DB_USER', 'mayasec'), help='Database user')
    parser.add_argument('--password', default=os.getenv('DB_PASSWORD', 'mayasec_password'), help='Database password')
    
    args = parser.parse_args()
    
    manager = MigrationManager(
        db_host=args.host,
        db_port=args.port,
        db_name=args.name,
        db_user=args.user,
        db_password=args.password
    )
    
    if args.command == 'run':
        success = manager.run()
        sys.exit(0 if success else 1)
    elif args.command == 'status':
        success = manager.status()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

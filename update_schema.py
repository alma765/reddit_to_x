"""
Database schema migration script to add the cleaned_title column to the Post table.
"""

import sqlite3
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration():
    """Add cleaned_title column to Post table"""
    db_path = "instance/redditbot.db"
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found at {db_path}")
        return False
    
    try:
        # Connect to the SQLite database
        logger.info(f"Connecting to database: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(post)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'cleaned_title' not in column_names:
            logger.info("Adding 'cleaned_title' column to post table")
            # Add the new column
            cursor.execute("ALTER TABLE post ADD COLUMN cleaned_title TEXT")
            conn.commit()
            logger.info("Column 'cleaned_title' added successfully")
        else:
            logger.info("Column 'cleaned_title' already exists, skipping")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error updating database schema: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting database schema update")
    success = run_migration()
    if success:
        logger.info("Database schema updated successfully")
    else:
        logger.error("Failed to update database schema")
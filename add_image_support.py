"""
Database schema migration script to add image support to the Post table.
"""
import os
import sys
import logging
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable not set")
    sys.exit(1)

# Connect to the database
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()

def run_migration():
    """Add image support to Post table"""
    try:
        logger.info("Starting migration to add image support")
        
        # Add content_type column
        logger.info("Adding content_type column")
        session.execute('ALTER TABLE post ADD COLUMN IF NOT EXISTS content_type VARCHAR(10) DEFAULT \'video\'')
        
        # Add image_path column
        logger.info("Adding image_path column")
        session.execute('ALTER TABLE post ADD COLUMN IF NOT EXISTS image_path VARCHAR(255)')
        
        # Add image_size_bytes column
        logger.info("Adding image_size_bytes column")
        session.execute('ALTER TABLE post ADD COLUMN IF NOT EXISTS image_size_bytes INTEGER')
        
        # Commit the changes
        session.commit()
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    run_migration()
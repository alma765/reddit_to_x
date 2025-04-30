"""
This script cleans up existing duplicate entries in the database.
It will delete any post marked as a duplicate that was never actually posted to Twitter.
"""

import logging
from datetime import datetime
from app import app, db
from models import Post

logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clean_duplicate_entries():
    """
    Remove existing duplicate entries that were never posted to Twitter.
    A true duplicate should be content that was successfully posted to Twitter.
    """
    with app.app_context():
        # Find all entries marked as duplicates that were never posted to Twitter
        fake_duplicates = Post.query.filter(
            Post.error == True,
            Post.error_message.like("%Duplicate%"),
            Post.posted_to_twitter == False
        ).all()
        
        logger.info(f"Found {len(fake_duplicates)} 'duplicate' entries that were never posted to Twitter")
        
        # Delete these entries
        for post in fake_duplicates:
            logger.info(f"Deleting fake duplicate entry: {post.reddit_id} - {post.title}")
            db.session.delete(post)
        
        # Commit changes
        db.session.commit()
        logger.info(f"Successfully cleaned up {len(fake_duplicates)} fake duplicate entries")
        
        return len(fake_duplicates)

if __name__ == "__main__":
    num_cleaned = clean_duplicate_entries()
    print(f"Cleaned up {num_cleaned} fake duplicate entries from the database")
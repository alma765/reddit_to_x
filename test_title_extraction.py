"""
Test script for the title extraction functionality.
This script will fetch a few Reddit posts and demonstrate the title extraction feature.
"""

import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_title_extraction():
    """Test the Reddit title extraction and cleaning functionality"""
    try:
        # Import within function to avoid circular imports
        from bot.reddit_client import RedditClient
        
        # Initialize the Reddit client
        logger.info("Initializing Reddit client...")
        reddit_client = RedditClient()
        
        # Fetch some videos from Reddit
        subreddits = ['CombatFootage']
        posts_limit = 3  # Limit to 3 posts for testing
        
        logger.info(f"Fetching videos from r/{subreddits[0]}...")
        submissions = reddit_client.fetch_videos(subreddits=subreddits, limit=posts_limit)
        
        if not submissions:
            logger.warning("No video submissions found. Exiting.")
            return
            
        logger.info(f"Found {len(submissions)} video submissions")
        
        # Process each submission to extract and clean titles
        for idx, submission in enumerate(submissions, 1):
            logger.info(f"\nProcessing submission {idx}:")
            logger.info(f"Original Title: {submission.title}")
            
            # Extract metadata including cleaned title
            metadata = reddit_client.extract_post_metadata(submission)
            
            logger.info(f"Cleaned Title: {metadata['cleaned_title']}")
            logger.info(f"Tweet Title: {metadata['tweet_title']}")
            
            # Show other extracted metadata
            logger.info(f"Subreddit: r/{metadata['subreddit']}")
            logger.info(f"Author: {metadata['author']}")
            logger.info(f"Score: {metadata['score']}")
            logger.info(f"Upvote Ratio: {metadata['upvote_ratio']}")
            logger.info(f"Comments: {metadata['num_comments']}")
            
            if metadata['flair']:
                logger.info(f"Flair: {metadata['flair']}")
                
            logger.info(f"NSFW: {metadata['is_nsfw']}")
            logger.info(f"Original Content: {metadata['is_original_content'] or metadata['has_oc_tag']}")
            
            logger.info("-" * 80)
            
        logger.info("Test completed successfully!")
        
    except Exception as e:
        logger.exception(f"Test failed with error: {e}")

if __name__ == "__main__":
    test_title_extraction()
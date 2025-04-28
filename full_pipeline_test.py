import os
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import our modules
from bot.reddit_client import RedditClient
from bot.twitter_client import TwitterClient
from bot.video_processor import VideoProcessor

def test_full_pipeline():
    """Test the full Reddit-to-Twitter pipeline"""
    try:
        # Initialize clients
        reddit_client = RedditClient()
        twitter_client = TwitterClient(use_mock=False)  # Will fall back to mock if needed
        video_processor = VideoProcessor()
        
        # Fetch video posts from Reddit
        subreddits = ['CombatFootage']  # Focus on this subreddit
        posts_limit = 5  # Limit to 5 posts for testing
        
        logger.info(f"Fetching videos from subreddits: {', '.join(subreddits)}")
        submissions = reddit_client.fetch_videos(subreddits=subreddits, limit=posts_limit)
        
        logger.info(f"Found {len(submissions)} video submissions")
        
        if not submissions:
            logger.warning("No video submissions found")
            return
        
        # Process each submission
        for submission in submissions:
            logger.info(f"Processing submission: {submission.id} - {submission.title}")
            
            # Extract video URL
            video_url = reddit_client.get_video_url(submission)
            logger.info(f"Video URL: {video_url}")
            
            if not video_url:
                logger.warning(f"Could not extract video URL for {submission.id}")
                continue
            
            # Generate a filename for the video
            download_path = video_processor.generate_filename(submission.id)
            
            # Download the video
            downloaded_path = reddit_client.download_video(video_url, download_path)
            
            if not downloaded_path:
                logger.warning(f"Failed to download video for {submission.id}")
                continue
            
            # Validate the video
            validation = video_processor.validate_video(downloaded_path)
            
            # If the video is invalid, check if it's due to size
            if not validation['valid']:
                size_error = False
                if validation['error'] and "exceeds Twitter limit" in validation['error']:
                    size_error = True
                    logger.info(f"Video exceeds size limit, attempting compression: {validation['size_bytes']/1024/1024:.2f} MB")
                    
                    # Try to compress the video
                    compressed_path = video_processor.compress_video(downloaded_path)
                    if compressed_path:
                        logger.info(f"Successfully compressed video: {compressed_path}")
                        # Validate the compressed video
                        validation = video_processor.validate_video(compressed_path)
                        if validation['valid']:
                            # Update the path to the compressed version
                            downloaded_path = compressed_path
                            size_error = False
                
                # If compression failed or other validation error
                if not validation['valid']:
                    logger.warning(f"Video validation failed for {submission.id}: {validation['error']}")
                    
                    # Clean up invalid video if it exists
                    if os.path.exists(downloaded_path):
                        try:
                            os.remove(downloaded_path)
                            logger.info(f"Removed invalid video file: {downloaded_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove invalid video: {e}")
                    
                    continue
            
            # Extract metadata and generate a clean, tweet-friendly title
            logger.info("Extracting post metadata and generating tweet title...")
            post_metadata = reddit_client.extract_post_metadata(submission)
            
            # Log the original and cleaned titles
            logger.info(f"Original Title: {submission.title}")
            logger.info(f"Cleaned Title: {post_metadata['cleaned_title']}")
            
            # Use the tweet-friendly title
            post_text = post_metadata['tweet_title']
            
            # Make sure we don't exceed Twitter's character limit
            if len(post_text) > 280:
                max_length = 280 - (len(f"\n\nSource: https://reddit.com{submission.permalink}") + 5)
                post_text = post_text[:max_length] + f"...\n\nSource: https://reddit.com{submission.permalink}"
            
            logger.info(f"Using tweet text: {post_text}")
            
            # Post to Twitter
            try:
                tweet_result = twitter_client.post_video(downloaded_path, post_text)
                
                logger.info(f"Successfully posted video from {submission.id} to Twitter")
                logger.info(f"Tweet URL: {tweet_result.get('tweet_url', 'N/A')}")
                
                # We only want to post one video per test
                break
                
            except Exception as e:
                logger.error(f"Error posting to Twitter: {e}")
        
        # Clean up old videos
        video_processor.cleanup_old_videos()
        
    except Exception as e:
        logger.exception(f"Unexpected error in full pipeline test: {e}")

if __name__ == "__main__":
    test_full_pipeline()
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

def test_mock_pipeline():
    """
    Test the entire Reddit-to-Twitter pipeline using the mock Twitter client.
    This will download actual videos from Reddit but simulate posting to Twitter.
    """
    try:
        # Import within function to avoid circular imports
        from bot.reddit_client import RedditClient
        from bot.twitter_client import TwitterClient
        from bot.video_processor import VideoProcessor
        import app
        
        with app.app.app_context():
            # Initialize clients
            logger.info("Initializing Reddit client...")
            reddit_client = RedditClient()
            
            logger.info("Initializing Twitter client (with mock)...")
            twitter_client = TwitterClient(use_mock=True)  # Force mock mode
            
            logger.info("Initializing video processor...")
            video_processor = VideoProcessor()
            
            # Fetch videos from Reddit
            subreddits = ['CombatFootage']
            posts_limit = 3  # Limit to 3 posts for testing
            
            logger.info(f"Fetching videos from r/{subreddits[0]}...")
            submissions = reddit_client.fetch_videos(subreddits=subreddits, limit=posts_limit)
            
            if not submissions:
                logger.warning("No video submissions found. Exiting.")
                return
                
            logger.info(f"Found {len(submissions)} video submissions")
            
            # Process one submission
            submission = submissions[0]
            logger.info(f"Processing submission: {submission.id} - {submission.title}")
            
            # Extract video URL
            video_url = reddit_client.get_video_url(submission)
            if not video_url:
                logger.error("Could not extract video URL. Exiting.")
                return
                
            logger.info(f"Video URL: {video_url}")
            
            # Generate a filename for the video
            download_path = video_processor.generate_filename(submission.id)
            
            # Download the video
            logger.info(f"Downloading video to {download_path}...")
            downloaded_path = reddit_client.download_video(video_url, download_path)
            
            if not downloaded_path:
                logger.error("Failed to download video. Exiting.")
                return
                
            logger.info(f"Video downloaded successfully: {downloaded_path}")
            
            # Validate the video
            logger.info("Validating video...")
            validation = video_processor.validate_video(downloaded_path)
            
            # Try compression if needed
            if not validation['valid'] and "exceeds Twitter limit" in validation.get('error', ''):
                size_mb = validation['size_bytes'] / (1024 * 1024)
                logger.info(f"Video exceeds size limit ({size_mb:.2f}MB), attempting compression...")
                
                compressed_path = video_processor.compress_video(downloaded_path)
                if compressed_path:
                    logger.info(f"Successfully compressed video: {compressed_path}")
                    
                    # Validate the compressed video
                    validation = video_processor.validate_video(compressed_path)
                    if validation['valid']:
                        downloaded_path = compressed_path
                    else:
                        logger.error(f"Compressed video validation failed: {validation.get('error')}")
                        return
                else:
                    logger.error("Compression failed")
                    return
            elif not validation['valid']:
                logger.error(f"Video validation failed: {validation.get('error')}")
                return
                
            # Video is now valid
            logger.info(f"Video validated: {downloaded_path} ({validation['size_bytes']/1024/1024:.2f}MB, {validation['duration']:.2f}s)")
            
            # Create post text
            post_text = f"{submission.title}\n\nSource: https://reddit.com{submission.permalink}"
            
            # Post to (mock) Twitter
            logger.info("Posting to Twitter (simulated)...")
            result = twitter_client.post_video(downloaded_path, post_text)
            
            logger.info(f"Mock tweet created: {result.get('tweet_url')}")
            logger.info("Test completed successfully!")
            
    except Exception as e:
        logger.exception(f"Test failed with error: {e}")

if __name__ == "__main__":
    test_mock_pipeline()
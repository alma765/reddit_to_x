import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import our modules
from bot.twitter_client import TwitterClient

def test_twitter_video_post():
    """Test posting a video to Twitter"""
    
    # Check if a video path is provided
    if len(sys.argv) < 2:
        print("Usage: python test_twitter_post.py <path_to_video_file>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    # Check if file exists
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        sys.exit(1)
    
    # Get file size
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    logger.info(f"Testing with video: {video_path} ({file_size_mb:.2f} MB)")
    
    try:
        # Initialize Twitter client
        logger.info("Initializing Twitter client...")
        twitter_client = TwitterClient()
        
        # Post video
        logger.info(f"Posting video to Twitter: {video_path}")
        post_text = "Test post from Reddit to Twitter Bot"
        
        result = twitter_client.post_video(video_path, post_text)
        
        logger.info(f"Successfully posted to Twitter!")
        logger.info(f"Tweet ID: {result['tweet_id']}")
        logger.info(f"Tweet URL: {result['tweet_url']}")
        
    except Exception as e:
        logger.exception(f"Error posting to Twitter: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_twitter_video_post()
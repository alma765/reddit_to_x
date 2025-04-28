import os
import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import just the Twitter client
sys.path.append('.')
from bot.twitter_client import TwitterClient

def test_twitter_post():
    """Test posting a video to Twitter directly"""
    try:
        # Create Twitter client
        twitter_client = TwitterClient(use_mock=False)
        
        # Find a small video from the downloads folder
        videos = []
        for filename in os.listdir("./downloads"):
            if filename.endswith(".mp4"):
                video_path = os.path.join("./downloads", filename)
                # Get file size
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                if file_size_mb < 15:  # Make sure it's under Twitter's size limit
                    videos.append((video_path, file_size_mb))
        
        if not videos:
            logger.error("No suitable videos found in downloads folder")
            return
        
        # Sort by size to get smallest one for faster upload during testing
        videos.sort(key=lambda x: x[1])
        video_path, size_mb = videos[0]
        
        logger.info(f"Found video: {video_path} ({size_mb:.2f} MB)")
        
        # Test posting to Twitter
        try:
            # Post text that follows Twitter's guidelines
            post_text = f"Combat footage from Reddit r/CombatFootage - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Post to Twitter
            result = twitter_client.post_video(video_path, post_text)
            
            logger.info(f"Twitter posting result: {result}")
            logger.info(f"Tweet URL: {result.get('tweet_url', 'N/A')}")
            
        except Exception as e:
            logger.error(f"Error posting to Twitter: {str(e)}")
            raise
    
    except Exception as e:
        logger.exception(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_twitter_post()
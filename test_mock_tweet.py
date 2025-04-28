import os
import sys
import logging
import uuid
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock Twitter client
class MockTwitterClient:
    def __init__(self):
        logger.info("Mock Twitter client initialized")
    
    def post_video(self, video_path, text=None):
        """Simulate posting a video to Twitter"""
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Get file size
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        
        # Generate mock tweet ID
        mock_tweet_id = str(uuid.uuid4()).replace('-', '')[:16]
        mock_tweet_url = f"https://twitter.com/user/status/{mock_tweet_id}"
        
        logger.info(f"MOCK: Would post video ({file_size_mb:.2f} MB) to Twitter")
        logger.info(f"MOCK: Tweet text: {text[:50] if text else 'No text'}")
        logger.info(f"MOCK: Tweet ID: {mock_tweet_id}")
        logger.info(f"MOCK: Tweet URL: {mock_tweet_url}")
        
        return {
            'tweet_id': mock_tweet_id,
            'tweet_url': mock_tweet_url
        }

# Test with an existing video
def test_mock_post():
    # Find a video file from the downloads folder
    videos = []
    for filename in os.listdir("./downloads"):
        if filename.endswith(".mp4"):
            videos.append(os.path.join("./downloads", filename))
    
    if not videos:
        logger.error("No videos found in downloads folder")
        return
    
    # Sort by size to get the smallest one
    videos.sort(key=lambda x: os.path.getsize(x))
    video_path = videos[0]
    
    logger.info(f"Found video: {video_path}")
    
    # Create mock client
    client = MockTwitterClient()
    
    # Test posting
    try:
        result = client.post_video(
            video_path,
            "Test post from Reddit to Twitter Bot"
        )
        
        logger.info(f"Mock posting successful: {result}")
    except Exception as e:
        logger.error(f"Error in mock posting: {e}")

if __name__ == "__main__":
    test_mock_post()
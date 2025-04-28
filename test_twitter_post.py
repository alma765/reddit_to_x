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
from bot.twitter_client import TwitterClient
from models import Post, db

def test_twitter_video_post():
    """Test posting a video to Twitter"""
    try:
        # Find a video file from the downloads folder that hasn't been posted yet
        import app  # This initializes the app and db
        
        with app.app.app_context():
            # Create Twitter client - attempt to use real credentials
            twitter_client = TwitterClient(use_mock=False)
            
            # Find an existing video in the downloads folder
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
                
                # If successful, record in database
                video_id = os.path.basename(video_path).split('.')[0]
                post = Post.query.filter_by(reddit_id=video_id).first()
                
                if post:
                    post.posted_to_twitter = True
                    post.twitter_post_id = result.get('tweet_id')
                    post.twitter_post_url = result.get('tweet_url')
                    post.processed_at = datetime.utcnow()
                    db.session.commit()
                    logger.info(f"Updated post record for {video_id}")
                
            except Exception as e:
                logger.error(f"Error posting to Twitter: {str(e)}")
                raise
    
    except Exception as e:
        logger.exception(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_twitter_video_post()
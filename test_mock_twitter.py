import os
import sys
import logging
import json
from datetime import datetime, timedelta
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# First import app, since it initializes everything
import app

# Import our modules
from bot.reddit_client import RedditClient
from bot.video_processor import VideoProcessor
from models import Post, db

class MockTwitterClient:
    def __init__(self):
        logger.info("Mock Twitter client initialized")
    
    def post_video(self, video_path, text=None):
        """
        Simulate posting a video to Twitter
        
        Args:
            video_path (str): Path to the video file
            text (str): Text to accompany the post
            
        Returns:
            dict: Mock response with tweet ID and URL
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Get file size
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        
        # Generate mock tweet ID
        mock_tweet_id = str(uuid.uuid4()).replace('-', '')[:16]
        mock_tweet_url = f"https://twitter.com/user/status/{mock_tweet_id}"
        
        logger.info(f"MOCK: Would post video ({file_size_mb:.2f} MB) to Twitter")
        logger.info(f"MOCK: Tweet text: {text[:50]}...")
        logger.info(f"MOCK: Tweet ID: {mock_tweet_id}")
        logger.info(f"MOCK: Tweet URL: {mock_tweet_url}")
        
        return {
            'tweet_id': mock_tweet_id,
            'tweet_url': mock_tweet_url
        }

def process_and_post_videos():
    """Process and mock-post videos from Reddit to Twitter"""
    try:
        logger.info("Starting Reddit-to-Twitter test with mock Twitter client")
        
        # Initialize clients
        reddit_client = RedditClient()
        video_processor = VideoProcessor()
        twitter_client = MockTwitterClient()
        
        # Fetch video posts from Reddit
        subreddits = ['CombatFootage']  # Focus on this subreddit
        posts_limit = 3  # Limit to 3 posts
        submissions = reddit_client.fetch_videos(subreddits=subreddits, limit=posts_limit)
        
        logger.info(f"Found {len(submissions)} video submissions")
        
        # Process each submission
        for submission in submissions:
            # Check if we've already processed this submission
            existing_post = Post.query.filter_by(reddit_id=submission.id).first()
            if existing_post and existing_post.posted_to_twitter:
                logger.info(f"Already processed submission {submission.id}")
                continue
                
            logger.info(f"Processing submission: {submission.id} - {submission.title}")
            
            # Create or update database record
            post = existing_post or Post(
                reddit_id=submission.id,
                reddit_url=f"https://reddit.com{submission.permalink}",
                title=submission.title,
                subreddit=submission.subreddit.display_name,
                author=submission.author.name if submission.author else "[deleted]",
                created_at=datetime.utcnow()
            )
            
            # Extract video URL
            video_url = reddit_client.get_video_url(submission)
            logger.info(f"Video URL: {video_url}")
            
            if not video_url:
                post.error = True
                post.error_message = "Could not extract video URL"
                db.session.add(post)
                db.session.commit()
                logger.warning(f"Could not extract video URL for {submission.id}")
                continue
            
            # Generate a filename for the video
            download_path = video_processor.generate_filename(submission.id)
            
            # Download the video
            downloaded_path = reddit_client.download_video(video_url, download_path)
            
            if not downloaded_path:
                post.error = True
                post.error_message = "Failed to download video"
                db.session.add(post)
                db.session.commit()
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
                    
                    # Try to compress the video (with a timeout)
                    try:
                        compressed_path = video_processor.compress_video(downloaded_path)
                        if compressed_path:
                            logger.info(f"Successfully compressed video: {compressed_path}")
                            # Validate the compressed video
                            validation = video_processor.validate_video(compressed_path)
                            if validation['valid']:
                                # Update the path to the compressed version
                                downloaded_path = compressed_path
                                size_error = False
                    except Exception as e:
                        logger.error(f"Compression error: {e}")
                
                # If compression failed or other validation error
                if not validation['valid']:
                    post.error = True
                    post.error_message = validation['error']
                    post.video_path = downloaded_path
                    post.video_size_bytes = validation['size_bytes']
                    post.video_duration_seconds = validation['duration']
                    db.session.add(post)
                    db.session.commit()
                    logger.warning(f"Video validation failed for {submission.id}: {validation['error']}")
                    
                    # Clean up invalid video if it exists
                    if os.path.exists(downloaded_path) and "downloaded" not in downloaded_path:
                        try:
                            os.remove(downloaded_path)
                            logger.info(f"Removed invalid video file: {downloaded_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove invalid video: {e}")
                    
                    continue
            
            # Update post with video info
            post.video_path = downloaded_path
            post.video_size_bytes = validation['size_bytes']
            post.video_duration_seconds = validation['duration']
            
            # Prepare post text
            post_text = f"{submission.title}\n\nSource: https://reddit.com{submission.permalink}"
            
            # Post to (mock) Twitter
            try:
                tweet_result = twitter_client.post_video(downloaded_path, post_text)
                
                # Update post with Twitter info
                post.posted_to_twitter = True
                post.twitter_post_id = tweet_result['tweet_id']
                post.twitter_post_url = tweet_result['tweet_url']
                post.processed_at = datetime.utcnow()
                
                db.session.add(post)
                db.session.commit()
                
                logger.info(f"Successfully processed video from {submission.id}")
                
                # We only want to post one video per run to simulate real behavior
                break
                
            except Exception as e:
                logger.error(f"Error posting to Twitter: {e}")
                post.error = True
                post.error_message = str(e)
                db.session.add(post)
                db.session.commit()
        
        # Clean up old videos
        video_processor.cleanup_old_videos()
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")

if __name__ == "__main__":
    with app.app.app_context():
        process_and_post_videos()
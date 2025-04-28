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

# First import app, since it initializes everything
import app

# Now import other modules
from bot.reddit_client import RedditClient
from bot.video_processor import VideoProcessor
from models import Post, db

def fetch_and_validate_videos():
    """Fetch videos from Reddit and validate them without posting to Twitter"""
    try:
        logger.info("Starting Reddit video fetching test")
        
        # Initialize clients
        reddit_client = RedditClient()
        video_processor = VideoProcessor()
        
        # Fetch video posts from Reddit
        subreddits = ['CombatFootage']  # Focus on this subreddit
        submissions = reddit_client.fetch_videos(subreddits=subreddits, limit=5)
        
        logger.info(f"Found {len(submissions)} video submissions")
        
        # Process each submission
        for submission in submissions:
            # Check if we've already processed this submission
            existing_post = Post.query.filter_by(reddit_id=submission.id).first()
            if existing_post:
                logger.info(f"Already processed submission {submission.id}")
                continue
                
            logger.info(f"Processing submission: {submission.id} - {submission.title}")
            
            # Create database record
            post = Post(
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
                    post.error = True
                    post.error_message = validation['error']
                    post.video_path = downloaded_path
                    post.video_size_bytes = validation['size_bytes']
                    post.video_duration_seconds = validation['duration']
                    db.session.add(post)
                    db.session.commit()
                    logger.warning(f"Video validation failed for {submission.id}: {validation['error']}")
                    
                    # Clean up invalid video if it exists
                    if os.path.exists(downloaded_path):
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
            
            # Mark as ready to post (but we won't actually post in this test)
            post.processed_at = datetime.utcnow()
            post.posted_to_twitter = False
            
            db.session.add(post)
            db.session.commit()
            
            logger.info(f"Successfully processed video from {submission.id}")
            logger.info(f"Video info: Duration={validation['duration']:.2f}s, Size={validation['size_bytes']/1024/1024:.2f}MB")
            
        # Clean up old videos
        video_processor.cleanup_old_videos()
        
    except Exception as e:
        logger.exception("Unexpected error in fetch_and_validate_videos")

if __name__ == "__main__":
    with app.app.app_context():
        fetch_and_validate_videos()
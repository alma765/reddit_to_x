import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import db
from models import Post
from bot.video_processor import VideoProcessor
from config import (
    SUBREDDITS,
    POSTS_LIMIT,
    POST_INTERVAL_MINUTES,
    DOWNLOAD_FOLDER
)

logger = logging.getLogger(__name__)

# Initialize video processor
video_processor = VideoProcessor(DOWNLOAD_FOLDER)

# Declare clients that will be initialized when needed
reddit_client = None
twitter_client = None

def process_and_post():
    """
    Main function to fetch Reddit videos and post them to Twitter
    """
    global reddit_client, twitter_client
    
    logger.info("Starting Reddit video processing job")
    
    try:
        # Initialize Reddit client if not already done
        if reddit_client is None:
            try:
                from bot.reddit_client import RedditClient
                reddit_client = RedditClient()
                logger.info("Reddit client initialized successfully")
            except ValueError as e:
                logger.error(f"Could not initialize Reddit client: {e}")
                return
        
        # Initialize Twitter client if not already done
        if twitter_client is None:
            try:
                from bot.twitter_client import TwitterClient
                # Use mock Twitter client when real authentication fails
                twitter_client = TwitterClient(use_mock=False)  # Will automatically fall back to mock if auth fails
                
                if twitter_client.use_mock:
                    logger.warning("Using mock Twitter client because authentication failed")
                    logger.warning("Videos will be processed but posts will be simulated, not actually sent to Twitter")
                    logger.warning("To fix this, update Twitter API credentials in the environment variables")
                else:
                    logger.info("Twitter client initialized successfully with real authentication")
            except Exception as e:
                logger.error(f"Could not initialize Twitter client: {e}")
                logger.error("Continuing with mock Twitter client as fallback")
                # Create mock client directly
                from bot.twitter_client import MockTwitterClient
                twitter_client = MockTwitterClient()
        
        # Fetch video posts from Reddit
        try:
            submissions = reddit_client.fetch_videos(SUBREDDITS, POSTS_LIMIT)
        except Exception as e:
            logger.error(f"Error fetching videos from Reddit: {e}")
            return
        
        if not submissions:
            logger.info("No video submissions found")
            return
        
        # Find posts we haven't processed yet
        for submission in submissions:
            # Check if we've already processed this post
            existing_post = db.session.query(Post).filter_by(reddit_id=submission.id).first()
            
            if existing_post:
                logger.debug(f"Skipping already processed submission: {submission.id}")
                continue
            
            logger.info(f"Processing new submission: {submission.id} - {submission.title}")
            
            # Create a new post record
            post = Post(
                reddit_id=submission.id,
                reddit_url=submission.url,
                title=submission.title,
                subreddit=submission.subreddit.display_name,
                author=submission.author.name if submission.author else "[deleted]",
                created_at=datetime.utcnow()
            )
            
            try:
                # Get the direct video URL
                video_url = reddit_client.get_video_url(submission)
                if not video_url:
                    post.error = True
                    post.error_message = "Could not extract video URL"
                    db.session.add(post)
                    db.session.commit()
                    logger.warning(f"Could not extract video URL for {submission.id}")
                    continue
                
                # Generate a filename and download the video
                video_path = video_processor.generate_filename(submission.id)
                downloaded_path = reddit_client.download_video(video_url, video_path)
                
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
                
                # Prepare post text
                post_text = f"{submission.title}\n\nSource: https://reddit.com{submission.permalink}"
                
                # Post to Twitter
                tweet_result = twitter_client.post_video(downloaded_path, post_text)
                
                # Update post with Twitter info
                post.posted_to_twitter = True
                post.twitter_post_id = tweet_result['tweet_id']
                post.twitter_post_url = tweet_result['tweet_url']
                post.processed_at = datetime.utcnow()
                
                db.session.add(post)
                db.session.commit()
                
                logger.info(f"Successfully posted video from {submission.id} to Twitter")
                
                # We only want to post one video per run, so exit after first success
                break
                
            except Exception as e:
                logger.exception(f"Error processing submission {submission.id}")
                
                # Update post with error info
                post.error = True
                post.error_message = str(e)
                db.session.add(post)
                db.session.commit()
        
        # Clean up old videos
        video_processor.cleanup_old_videos()
        
    except Exception as e:
        logger.exception("Unexpected error in process_and_post job")

# Create scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    process_and_post,
    IntervalTrigger(minutes=POST_INTERVAL_MINUTES),
    id='reddit_to_twitter',
    replace_existing=True
)

# Add a one-time job to run at startup
scheduler.add_job(
    process_and_post,
    'date',
    run_date=datetime.now() + timedelta(seconds=10),  # Run 10 seconds after startup
    id='startup_job'
)

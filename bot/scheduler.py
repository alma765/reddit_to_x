import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import tweepy  # Import tweepy for rate limit exception handling

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
    Main function to fetch Reddit content (videos and images) and post them to Twitter
    """
    global reddit_client, twitter_client
    
    logger.info("Starting Reddit content processing job")
    
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
                twitter_client = TwitterClient()
                logger.info("Twitter client initialized successfully")
            except Exception as e:
                logger.error(f"Could not initialize Twitter client: {e}")
                # If we hit rate limits or have authentication issues, record the error and retry later
                if "429" in str(e) or "Too Many Requests" in str(e):
                    logger.error("Twitter rate limit reached. Will retry in 60 minutes.")
                    return  # Exit processing and retry on next scheduled run
                elif "401" in str(e):
                    logger.error("Twitter authentication failed. Please check your API credentials.")
                    return  # Exit processing as credentials are invalid
                else:
                    logger.error(f"Unknown Twitter error: {e}")
                    return  # Exit processing for any other Twitter API issues
        
        # Fetch content (videos and images) from Reddit
        try:
            # Fetch both videos and images
            submissions = reddit_client.fetch_content(SUBREDDITS, POSTS_LIMIT, content_type="all")
        except Exception as e:
            logger.error(f"Error fetching content from Reddit: {e}")
            return
        
        if not submissions:
            logger.info("No submissions found")
            return
        
        # Find posts we haven't processed yet
        for submission in submissions:
            # Check if we've already processed this post
            existing_post = db.session.query(Post).filter_by(reddit_id=submission.id).first()
            
            if existing_post:
                logger.debug(f"Skipping already processed submission: {submission.id}")
                continue
                
            # Determine content type (video, image, or gallery)
            content_type = "unknown"
            media_url = None
            is_gallery = False
            
            # Check for gallery (special case of image)
            if hasattr(submission, 'is_gallery') and submission.is_gallery:
                content_type = "gallery"
                is_gallery = True
                # No media_url needed for gallery, we'll handle it differently
            # Check for video
            elif reddit_client._has_video(submission):
                content_type = "video"
                media_url = reddit_client.get_video_url(submission)
            # Check for single image
            elif reddit_client._has_image(submission):
                content_type = "image"
                media_url = reddit_client.get_image_url(submission)
            
            # For galleries, we don't need a media_url as we'll get all images separately
            if not media_url and content_type != "gallery":
                logger.warning(f"Could not extract media URL for {submission.id}")
                continue
                
            # For non-gallery posts, check for similar content by URL pattern
            similar_posts = None
            if content_type != "gallery" and media_url:
                media_url_pattern = media_url.split('?')[0]  # Remove query parameters
                similar_posts = db.session.query(Post).filter(
                    Post.reddit_url.like(f"%{media_url_pattern}%")
                ).first()
            
            if similar_posts:
                logger.warning(f"Skipping submission {submission.id} with similar {content_type} URL pattern")
                
                # Record as duplicate but don't post
                post = Post(
                    reddit_id=submission.id,
                    reddit_url=submission.url,
                    title=submission.title,
                    subreddit=submission.subreddit.display_name,
                    author=submission.author.name if submission.author else "[deleted]",
                    content_type=content_type,
                    created_at=datetime.utcnow(),
                    error=True,
                    error_message=f"Duplicate {content_type} content detected",
                    processed_at=datetime.utcnow()
                )
                db.session.add(post)
                db.session.commit()
                continue
            
            logger.info(f"Processing new submission: {submission.id} - {submission.title}")
            
            # Create a new post record
            post = Post(
                reddit_id=submission.id,
                reddit_url=submission.url,
                title=submission.title,
                subreddit=submission.subreddit.display_name,
                author=submission.author.name if submission.author else "[deleted]",
                content_type=content_type,
                created_at=datetime.utcnow()
            )
            
            try:
                downloaded_path = None
                
                # Process based on content type
                if content_type == "video":
                    # Process video content
                    logger.info(f"Processing video content for {submission.id}")
                    
                    # Generate a filename and download the video
                    video_path = video_processor.generate_filename(submission.id)
                    downloaded_path = reddit_client.download_video(media_url, video_path)
                    
                    if not downloaded_path:
                        post.error = True
                        post.error_message = "Failed to download video"
                        db.session.add(post)
                        db.session.commit()
                        logger.warning(f"Failed to download video for {submission.id}")
                        continue
                    
                    # Check for duplicate content
                    if video_processor.is_duplicate_content(downloaded_path):
                        logger.warning(f"Duplicate video content detected for {submission.id}")
                        post.error = True
                        post.error_message = "Duplicate video content detected"
                        post.processed_at = datetime.utcnow()
                        db.session.add(post)
                        db.session.commit()
                        
                        # Clean up duplicate video
                        try:
                            os.remove(downloaded_path)
                            logger.info(f"Removed duplicate video file: {downloaded_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove duplicate video: {e}")
                        
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
                                    # Check for duplicate content again with compressed video
                                    if video_processor.is_duplicate_content(compressed_path):
                                        logger.warning(f"Duplicate video content detected after compression for {submission.id}")
                                        post.error = True
                                        post.error_message = "Duplicate video content detected after compression"
                                        post.processed_at = datetime.utcnow()
                                        db.session.add(post)
                                        db.session.commit()
                                        
                                        # Clean up duplicate videos
                                        try:
                                            os.remove(downloaded_path)
                                            os.remove(compressed_path)
                                            logger.info(f"Removed duplicate video files after compression")
                                        except Exception as e:
                                            logger.error(f"Failed to remove duplicate videos: {e}")
                                        
                                        continue
                                        
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
                    
                elif content_type == "image":
                    # Process image content
                    logger.info(f"Processing image content for {submission.id}")
                    
                    # Generate a filename and download the image
                    image_path = video_processor.generate_filename(submission.id, extension=".jpg")
                    downloaded_path = reddit_client.download_image(media_url, image_path)
                    
                    if not downloaded_path:
                        post.error = True
                        post.error_message = "Failed to download image"
                        db.session.add(post)
                        db.session.commit()
                        logger.warning(f"Failed to download image for {submission.id}")
                        continue
                    
                    # Get image file size
                    image_size = os.path.getsize(downloaded_path)
                    
                    # Update post with image info
                    post.image_path = downloaded_path
                    post.image_size_bytes = image_size
                    
                    # Check if image is too large for Twitter (5MB limit)
                    if image_size > 5 * 1024 * 1024:
                        post.error = True
                        post.error_message = "Image exceeds Twitter size limit (5MB)"
                        db.session.add(post)
                        db.session.commit()
                        logger.warning(f"Image too large for Twitter: {image_size/1024/1024:.2f} MB")
                        
                        # Clean up oversized image
                        try:
                            os.remove(downloaded_path)
                            logger.info(f"Removed oversized image file: {downloaded_path}")
                        except Exception as e:
                            logger.error(f"Failed to remove oversized image: {e}")
                        
                        continue
                
                # Extract metadata and generate a clean, tweet-friendly title
                logger.info("Extracting post metadata and generating tweet title...")
                post_metadata = reddit_client.extract_post_metadata(submission)
                
                # Store the cleaned title in our database
                post.cleaned_title = post_metadata['cleaned_title']
                
                # Use the tweet-friendly title
                post_text = post_metadata['tweet_title']
                
                # Make sure we don't exceed Twitter's character limit
                if len(post_text) > 280:
                    # Truncate text
                    max_length = 280 - 3  # Room for ellipsis
                    post_text = post_text[:max_length] + "..."
                
                logger.info(f"Using tweet text: {post_text}")
                
                # We have already imported tweepy at the top of the file
                    
                # Initialize tweet_result variable
                tweet_result = None
                
                # Process based on content type and post to Twitter
                try:
                    if content_type == "video":
                        # Post video
                        tweet_result = twitter_client.post_video(downloaded_path, post_text)
                        logger.info(f"Successfully posted video from {submission.id} to Twitter")
                        
                    elif content_type == "image":
                        # Post single image 
                        tweet_result = twitter_client.post_image(downloaded_path, post_text)
                        logger.info(f"Successfully posted image from {submission.id} to Twitter")
                        
                    elif content_type == "gallery":
                        # Process gallery post
                        logger.info(f"Processing gallery post for {submission.id}")
                        
                        # Generate a base filename for gallery images
                        base_image_path = video_processor.generate_filename(submission.id, extension="")
                        
                        # Download all gallery images
                        gallery_image_paths = reddit_client.download_gallery_images(submission, base_image_path)
                        
                        if not gallery_image_paths:
                            post.error = True
                            post.error_message = "Failed to download gallery images"
                            post.processed_at = datetime.utcnow()
                            db.session.add(post)
                            db.session.commit()
                            logger.warning(f"Failed to download gallery images for {submission.id}")
                            continue
                        
                        # Store the path to the first image in the post record
                        post.image_path = gallery_image_paths[0]
                        post.image_size_bytes = os.path.getsize(gallery_image_paths[0])
                        
                        # Set first image metadata in post record
                        if len(gallery_image_paths) > 1:
                            # Indicate it's one of multiple images
                            logger.info(f"Posting gallery with {len(gallery_image_paths)} images as a Twitter thread")
                            
                            # Create tweet texts for the thread (first tweet uses main text)
                            continue_texts = []
                            for i in range(1, len(gallery_image_paths)):
                                # Create a simplified continuation tweet text
                                # Strip any content type indicators first
                                base_text = post_text
                                base_text = base_text.replace(" [Photo]", "").replace(" [Gallery]", "").replace(" [Video]", "")
                                
                                # Add clear numbering for gallery images
                                # Always show the current image number and total count
                                continue_texts.append(f"Image {i+1}/{len(gallery_image_paths)}")
                            
                            # Create a thread with all gallery images
                            thread_result = twitter_client.create_thread_with_images(
                                gallery_image_paths,
                                main_text=post_text,
                                continue_texts=continue_texts
                            )
                            
                            tweet_result = {
                                'tweet_id': thread_result['first_tweet_id'],
                                'tweet_url': thread_result['first_tweet_url']
                            }
                            logger.info(f"Successfully posted gallery thread with {len(gallery_image_paths)} images from {submission.id} to Twitter")
                        else:
                            # If there's only one image, post normally
                            tweet_result = twitter_client.post_image(gallery_image_paths[0], post_text)
                            logger.info(f"Posted single image from gallery {submission.id} to Twitter")
                
                except Exception as e:
                    error_msg = str(e)
                    
                    # Check for Twitter rate limit errors
                    if "429" in error_msg or "Too Many Requests" in error_msg or "rate limit" in error_msg.lower():
                        post.error = True
                        post.error_message = "Twitter rate limit reached. Will retry in 60 minutes."
                        post.processed_at = datetime.utcnow()
                        db.session.add(post)
                        db.session.commit()
                        logger.error(f"Twitter rate limit reached when posting {content_type} for {submission.id}")
                        # Exit the entire process early - we'll retry in 60 minutes
                        return
                    else:
                        # Handle other Twitter API errors
                        post.error = True
                        post.error_message = f"Twitter API error: {error_msg}"
                        post.processed_at = datetime.utcnow()
                        db.session.add(post)
                        db.session.commit()
                        logger.error(f"Twitter API error when posting {content_type} for {submission.id}: {error_msg}")
                        continue
                        
                # Check if we got a valid tweet result
                if not tweet_result:
                    post.error = True
                    post.error_message = "Failed to get Twitter post result"
                    post.processed_at = datetime.utcnow()
                    db.session.add(post)
                    db.session.commit()
                    logger.error(f"No tweet result for {submission.id}")
                    continue
                
                # Update post with Twitter info
                post.posted_to_twitter = True
                post.twitter_post_id = tweet_result['tweet_id']
                post.twitter_post_url = tweet_result['tweet_url']
                post.processed_at = datetime.utcnow()
                
                db.session.add(post)
                db.session.commit()
                
                # We only want to post one item per run, so exit after first success
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

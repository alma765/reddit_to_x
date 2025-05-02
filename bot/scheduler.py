import logging
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import tweepy  # Import tweepy for rate limit exception handling

# Import db and app to handle application context
from app import db, app

# Create the video processor import first
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

def fetch_reddit_content():
    """
    Main function to fetch Reddit content (videos and images) without posting to Twitter
    """
    global reddit_client
    
    # Ensure we're running within the Flask application context
    with app.app_context():
        logger.info("Starting Reddit content fetching job")
        
        try:
            # Initialize Reddit client if not already done
            if reddit_client is None:
                try:
                    from bot.reddit_client import RedditClient
                    reddit_client = RedditClient()
                    logger.info("Reddit client initialized successfully")
                    logger.info(f"Reddit client configuration: {reddit_client.reddit.config.__dict__}")
                    # Test the client by fetching a subreddit
                    test_subreddit = reddit_client.reddit.subreddit('CombatFootage')
                    logger.info(f"Successfully connected to subreddit: {test_subreddit.display_name}")
                except ValueError as e:
                    logger.error(f"Could not initialize Reddit client: {e}")
                    logger.error(f"Check your Reddit API credentials in .env file")
                    return jsonify({'success': False, 'error': 'Invalid Reddit API credentials'}), 400
                except Exception as e:
                    logger.error(f"Unexpected error initializing Reddit client: {e}")
                    logger.exception("Detailed error:")
                    return jsonify({'success': False, 'error': str(e)}), 500
            
            # Fetch content (videos and images) from Reddit
            try:
                logger.info(f"Fetching content from subreddits: {SUBREDDITS}")
                logger.info(f"Post limit: {POSTS_LIMIT}")
                submissions = reddit_client.fetch_content(SUBREDDITS, POSTS_LIMIT, content_type="all")
                logger.info(f"Found {len(submissions)} submissions")
                
                if not submissions:
                    logger.warning("No submissions found from Reddit")
                    return jsonify({'success': True, 'message': 'No content found'})
                
                # Process submissions and store in database
                from models import Post
                for submission in submissions:
                    try:
                        # Create a new post record
                        new_post = Post(
                            reddit_id=submission.id,
                            title=submission.title,
                            subreddit=submission.subreddit.display_name,
                            reddit_url=f"https://reddit.com{submission.permalink}",
                            content_type='video' if reddit_client._has_video(submission) else 'image',
                            created_at=datetime.utcnow()
                        )
                        
                        # Add to database
                        db.session.add(new_post)
                        db.session.commit()
                        logger.info(f"Added post to database: {new_post.title}")
                    except Exception as e:
                        logger.error(f"Error processing submission {submission.id}: {e}")
                        db.session.rollback()
                        continue
                
                return jsonify({'success': True, 'message': f'Found {len(submissions)} posts'})
            except Exception as e:
                logger.error(f"Error fetching content from Reddit: {e}")
                logger.exception("Detailed error:")
                return jsonify({'success': False, 'error': str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error in fetch_reddit_content: {e}")
            logger.exception("Detailed error:")
            return jsonify({'success': False, 'error': 'Internal server error'}), 500

            if not submissions:
                logger.info("No submissions found")
                return
            
            # Import the Post model here to avoid circular imports at module level
            from models import Post
            
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
                # BUT only consider previously SUCCESSFUL posts to Twitter as duplicates
                similar_posts = None
                if content_type != "gallery" and media_url:
                    media_url_pattern = media_url.split('?')[0]  # Remove query parameters
                    similar_posts = db.session.query(Post).filter(
                        Post.reddit_url.like(f"%{media_url_pattern}%") &
                        Post.posted_to_twitter == True  # Only count successful posts as duplicates
                    ).first()
                
                if similar_posts:
                    logger.warning(f"Skipping submission {submission.id} with similar {content_type} URL pattern that was previously posted to Twitter")
                    # Don't even add to the database, just skip it
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
                            logger.warning(f"Skipping submission {submission.id} - duplicate video content detected that was previously posted to Twitter")
                            
                            # Clean up duplicate video
                            try:
                                os.remove(downloaded_path)
                                logger.info(f"Removed duplicate video file: {downloaded_path}")
                            except Exception as e:
                                logger.error(f"Failed to remove duplicate video: {e}")
                            
                            # Don't add to database, just skip
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
                                            logger.warning(f"Skipping submission {submission.id} - duplicate video content detected after compression that was previously posted to Twitter")
                                            
                                            # Clean up duplicate videos
                                            try:
                                                os.remove(downloaded_path)
                                                os.remove(compressed_path)
                                                logger.info(f"Removed duplicate video files after compression")
                                            except Exception as e:
                                                logger.error(f"Failed to remove duplicate videos: {e}")
                                            
                                            # Don't add to database, just skip
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
                            continue
                            
                    elif content_type == "gallery":
                        # Process gallery content
                        logger.info(f"Processing gallery content for {submission.id}")
                        
                        # Generate a base filename for gallery images
                        gallery_base_path = video_processor.generate_filename(submission.id, extension="")
                        gallery_image_paths = reddit_client.download_gallery_images(submission, gallery_base_path)
                        
                        if not gallery_image_paths:
                            post.error = True
                            post.error_message = "Failed to download gallery images"
                            db.session.add(post)
                            db.session.commit()
                            logger.warning(f"Failed to download gallery images for {submission.id}")
                            continue
                            
                        # Update post with gallery info
                        post.image_path = gallery_image_paths[0]  # Store first image path
                        post.image_size_bytes = os.path.getsize(gallery_image_paths[0])
                        
                        # Add additional metadata about gallery
                        post.extra_data = {
                            'gallery_image_count': len(gallery_image_paths),
                            'gallery_image_paths': gallery_image_paths
                        }
                    
                    # Get post metadata from Reddit
                    metadata = reddit_client.extract_post_metadata(submission)
                    
                    # Clean the title to make it more readable
                    if metadata and 'cleaned_title' in metadata:
                        post.cleaned_title = metadata['cleaned_title']
                    
                    # Generate tweet text
                    post_text = ""
                    if post.cleaned_title:
                        post_text = post.cleaned_title
                    else:
                        post_text = post.title
                        
                    # Generate tweet text using the Reddit client's helper method
                    if metadata:
                        post_text = reddit_client.generate_tweet_title(metadata)
                        
                    # Try to post to Twitter
                    tweet_result = None
                    
                    try:
                        if content_type == "video":
                            # Post video to Twitter
                            tweet_result = twitter_client.post_video(downloaded_path, post_text)
                            logger.info(f"Posted video {submission.id} to Twitter")
                        
                        elif content_type == "image":
                            # Post image to Twitter
                            tweet_result = twitter_client.post_image(downloaded_path, post_text)
                            logger.info(f"Posted image {submission.id} to Twitter")
                            
                        elif content_type == "gallery":
                            # Check how many images we have in the gallery
                            if len(gallery_image_paths) > 1:
                                # Create a thread if we have multiple images
                                logger.info(f"Posting gallery with {len(gallery_image_paths)} images as a Twitter thread")
                                
                                # Create tweet texts for the thread (first tweet uses main text)
                                continue_texts = []
                                for i in range(1, len(gallery_image_paths)):
                                    # We no longer need to strip content type indicators since we don't add them anymore
                                    base_text = post_text
                                    
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
scheduler = BackgroundScheduler()

# Function definitions

def process_and_post():
    """
    Process fetched content and post to Twitter
    """
    global reddit_client
    
    # Ensure we're running within the Flask application context
    with app.app_context():
        logger.info("Starting content processing and posting job")
        
        try:
            # Initialize Reddit client if not already done
            if reddit_client is None:
                try:
                    from bot.reddit_client import RedditClient
                    reddit_client = RedditClient()
                    logger.info("Reddit client initialized successfully")
                except Exception as e:
                    logger.error(f"Could not initialize Reddit client: {e}")
                    return
            
            # Fetch content
            submissions = fetch_reddit_content()
            
            if not submissions:
                logger.warning("No submissions found for processing")
                return
            
            # Process each submission
            for submission in submissions:
                try:
                    # Check if this post has already been processed
                    existing_post = Post.query.filter_by(reddit_id=submission.id).first()
                    if existing_post:
                        logger.info(f"Skipping already processed post: {submission.id}")
                        continue
                    
                    # Create new post record
                    new_post = Post(
                        reddit_id=submission.id,
                        reddit_url=f"https://reddit.com{submission.permalink}",
                        title=submission.title,
                        subreddit=submission.subreddit.display_name,
                        content_type='video' if reddit_client._has_video(submission) else 'image'
                    )
                    db.session.add(new_post)
                    db.session.commit()
                    logger.info(f"Created new post record: {submission.id}")
                    
                    # Process the content (download, convert, etc.)
                    processed_content = process_content(submission)
                    
                    if processed_content:
                        # Post to Twitter
                        post_to_twitter(processed_content)
                except Exception as e:
                    logger.error(f"Error processing submission {submission.id}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Unexpected error in process_and_post: {e}")
            logger.exception("Detailed error:")

    return True


def process_content(submission):
    """
    Process the content of a submission
    """
    global reddit_client
    
    try:
        # Get post from database
        post = Post.query.filter_by(reddit_id=submission.id).first()
        if not post:
            logger.error(f"Post not found in database: {submission.id}")
            return None

        # Determine content type
        content_type = 'video' if reddit_client._has_video(submission) else 'image'
        
        if content_type == "video":
            # Process video content
            logger.info(f"Processing video content for {submission.id}")
            
            # Generate a filename and download the video
            video_path = video_processor.generate_filename(submission.id, extension=".mp4")
            downloaded_path = reddit_client.download_video(submission.url, video_path)
            
            if not downloaded_path:
                post.error = True
                post.error_message = "Failed to download video"
                db.session.add(post)
                db.session.commit()
                logger.warning(f"Failed to download video for {submission.id}")
                return None
            
            # Validate video
            validation = video_processor.validate_video(downloaded_path)
            
            if not validation['valid']:
                logger.warning(f"Video validation failed for {submission.id}: {validation['error']}")
                
                # Clean up invalid video if it exists
                if os.path.exists(downloaded_path):
                    try:
                        os.remove(downloaded_path)
                        logger.info(f"Removed invalid video file: {downloaded_path}")
                    except Exception as e:
                        logger.error(f"Failed to remove invalid video: {e}")
                
                post.error = True
                post.error_message = f"Video validation failed: {validation['error']}"
                db.session.add(post)
                db.session.commit()
                return None
            
            # Update post with video info
            post.video_path = downloaded_path
            post.video_size_bytes = validation['size_bytes']
            post.video_duration_seconds = validation['duration']
            
        elif content_type == "image":
            # Process image content
            logger.info(f"Processing image content for {submission.id}")
            
            # Generate a filename and download the image
            image_path = video_processor.generate_filename(submission.id, extension=".jpg")
            downloaded_path = reddit_client.download_image(submission.url, image_path)
            
            if not downloaded_path:
                post.error = True
                post.error_message = "Failed to download image"
                db.session.add(post)
                db.session.commit()
                logger.warning(f"Failed to download image for {submission.id}")
                return None
            
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
                return None
                
        # Get post metadata from Reddit
        metadata = reddit_client.extract_post_metadata(submission)
        
        # Clean the title to make it more readable
        if metadata and 'cleaned_title' in metadata:
            post.cleaned_title = metadata['cleaned_title']
        
        # Update post with content type
        post.content_type = content_type
        db.session.add(post)
        db.session.commit()
        
        return {
            'post': post,
            'downloaded_path': downloaded_path,
            'content_type': content_type
        }
        
    except Exception as e:
        logger.error(f"Error processing content for {submission.id}: {e}")
        return None


def post_to_twitter(processed_content):
    """
    Post processed content to Twitter
    """
    global twitter_client
    
    try:
        if twitter_client is None:
            from bot.twitter_client import TwitterClient
            twitter_client = TwitterClient()
            logger.info("Twitter client initialized successfully")
        
        post = processed_content['post']
        downloaded_path = processed_content['downloaded_path']
        content_type = processed_content['content_type']
        
        # Generate tweet text using the Reddit client's helper method
        metadata = reddit_client.extract_post_metadata(post.reddit_id)
        post_text = reddit_client.generate_tweet_title(metadata)
        
        # Add Twitter post URL placeholder
        post_text += "\n\nTwitter Post: "
        
        # Try to post to Twitter
        tweet_result = None
        
        try:
            if content_type == "video":
                # Post video to Twitter
                tweet_result = twitter_client.post_video(downloaded_path, post_text)
                logger.info(f"Posted video {post.reddit_id} to Twitter")
            
            elif content_type == "image":
                # Post image to Twitter
                tweet_result = twitter_client.post_image(downloaded_path, post_text)
                logger.info(f"Posted image {post.reddit_id} to Twitter")
            
        except Exception as e:
            error_msg = str(e)
            
            # Check for Twitter rate limit errors
            if "429" in error_msg or "Too Many Requests" in error_msg or "rate limit" in error_msg.lower():
                post.error = True
                post.error_message = "Twitter rate limit reached. Will retry in 60 minutes."
                post.processed_at = datetime.utcnow()
                post.status = 'error'
                post.error_details = error_msg
                db.session.add(post)
                db.session.commit()
                logger.error(f"Twitter rate limit reached when posting {content_type} for {post.reddit_id}")
                return False
            else:
                # Handle other Twitter API errors
                post.error = True
                post.error_message = f"Twitter API error: {error_msg}"
                post.processed_at = datetime.utcnow()
                post.status = 'error'
                post.error_details = error_msg
                db.session.add(post)
                db.session.commit()
                logger.error(f"Twitter API error when posting {content_type} for {post.reddit_id}: {error_msg}")
                return False
            
        # Check if we got a valid tweet result
        if not tweet_result:
            post.error = True
            post.error_message = "Failed to get Twitter post result"
            post.processed_at = datetime.utcnow()
            post.status = 'error'
            post.error_details = "Failed to get Twitter post result"
            db.session.add(post)
            db.session.commit()
            logger.error(f"No tweet result for {post.reddit_id}")
            return False
            
        # Update post with Twitter info and set status to posted
        post.posted_to_twitter = True
        post.twitter_post_id = tweet_result['tweet_id']
        post.twitter_post_url = tweet_result['tweet_url']
        post.processed_at = datetime.utcnow()
        post.status = 'posted'
        post.twitter_post_url = f"https://x.com/{tweet_result['screen_name']}/status/{tweet_result['tweet_id']}"
        
        # Update the post text with the actual Twitter URL
        post_text = post_text.replace("Twitter Post: ", f"Twitter Post: {post.twitter_post_url}\n")
        post.post_text = post_text
        
        db.session.add(post)
        db.session.commit()
        
        logger.info(f"Successfully posted content to Twitter: {post.reddit_id} - {post.twitter_post_url}")
        return True
        
    except Exception as e:
        logger.error(f"Error posting to Twitter: {e}")
        return False

def process_content(submission):
    """
    Process the content of a submission
    """
    # Determine content type
    content_type = submission.preview.get('reddit_video_preview') and "video" or submission.post_hint
    
    if content_type == "video":
        # Process video content
        logger.info(f"Processing video content for {submission.id}")
        
        # Generate a filename and download the video
        video_path = video_processor.generate_filename(submission.id, extension=".mp4")
        downloaded_path = reddit_client.download_video(submission.url, video_path)
        
        if not downloaded_path:
            post.error = True
            post.error_message = "Failed to download video"
            db.session.add(post)
            db.session.commit()
            logger.warning(f"Failed to download video for {submission.id}")
            return
        
        # Validate video
        validation = video_processor.validate_video(downloaded_path)
        
        if not validation['valid']:
            logger.warning(f"Video validation failed for {submission.id}: {validation['error']}")
            
            # Clean up invalid video if it exists
            if os.path.exists(downloaded_path):
                try:
                    os.remove(downloaded_path)
                    logger.info(f"Removed invalid video file: {downloaded_path}")
                except Exception as e:
                    logger.error(f"Failed to remove invalid video: {e}")
            
            return
        
        # Update post with video info
        post.video_path = downloaded_path
        post.video_size_bytes = validation['size_bytes']
        post.video_duration_seconds = validation['duration']
        
    elif content_type == "image":
        # Process image content
        logger.info(f"Processing image content for {submission.id}")
        
        # Generate a filename and download the image
        image_path = video_processor.generate_filename(submission.id, extension=".jpg")
        downloaded_path = reddit_client.download_image(submission.url, image_path)
        
        if not downloaded_path:
            post.error = True
            post.error_message = "Failed to download image"
            db.session.add(post)
            db.session.commit()
            logger.warning(f"Failed to download image for {submission.id}")
            return
        
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
            return
            
    elif content_type == "gallery":
        # Process gallery content
        logger.info(f"Processing gallery content for {submission.id}")
        
        # Generate a base filename for gallery images
        gallery_base_path = video_processor.generate_filename(submission.id, extension="")
        gallery_image_paths = reddit_client.download_gallery_images(submission, gallery_base_path)
        
        if not gallery_image_paths:
            post.error = True
            post.error_message = "Failed to download gallery images"
            db.session.add(post)
            db.session.commit()
            logger.warning(f"Failed to download gallery images for {submission.id}")
            return
            
        # Update post with gallery info
        post.image_path = gallery_image_paths[0]  # Store first image path
        post.image_size_bytes = os.path.getsize(gallery_image_paths[0])
        
        # Add additional metadata about gallery
        post.extra_data = {
            'gallery_image_count': len(gallery_image_paths),
            'gallery_image_paths': gallery_image_paths
        }
    
    # Get post metadata from Reddit
    metadata = reddit_client.extract_post_metadata(submission)
    
    # Clean the title to make it more readable
    if metadata and 'cleaned_title' in metadata:
        post.cleaned_title = metadata['cleaned_title']
    
    # Generate tweet text
    post_text = ""
    if post.cleaned_title:
        post_text = post.cleaned_title
    else:
        post_text = post.title
        
    # Generate tweet text using the Reddit client's helper method
    if metadata:
        post_text = reddit_client.generate_tweet_title(metadata)
        
    # Try to post to Twitter
    tweet_result = None
    
    try:
        if content_type == "video":
            # Post video to Twitter
            tweet_result = twitter_client.post_video(downloaded_path, post_text)
            logger.info(f"Posted video {submission.id} to Twitter")
        
        elif content_type == "image":
            # Post image to Twitter
            tweet_result = twitter_client.post_image(downloaded_path, post_text)
            logger.info(f"Posted image {submission.id} to Twitter")
            
        elif content_type == "gallery":
            # Check how many images we have in the gallery
            if len(gallery_image_paths) > 1:
                # Create a thread if we have multiple images
                logger.info(f"Posting gallery with {len(gallery_image_paths)} images as a Twitter thread")
                
                # Create tweet texts for the thread (first tweet uses main text)
                continue_texts = []
                for i in range(1, len(gallery_image_paths)):
                    # We no longer need to strip content type indicators since we don't add them anymore
                    base_text = post_text
                    
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
            return
        
    # Check if we got a valid tweet result
    if not tweet_result:
        post.error = True
        post.error_message = "Failed to get Twitter post result"
        post.processed_at = datetime.utcnow()
        db.session.add(post)
        db.session.commit()
        logger.error(f"No tweet result for {submission.id}")
        return
    
    # Update post with Twitter info
    post.posted_to_twitter = True
    post.twitter_post_id = tweet_result['tweet_id']
    post.twitter_post_url = tweet_result['tweet_url']
    post.processed_at = datetime.utcnow()
    
    db.session.add(post)
    db.session.commit()
    
    # We only want to post one item per run, so exit after first success
    return True

def post_to_twitter(processed_content):
    """
    Post processed content to Twitter
    """
    # Get post metadata from Reddit
    metadata = reddit_client.extract_post_metadata(submission)
    
    # Clean the title to make it more readable
    if metadata and 'cleaned_title' in metadata:
        post.cleaned_title = metadata['cleaned_title']
    
    # Generate tweet text
    post_text = ""
    if post.cleaned_title:
        post_text = post.cleaned_title
    else:
        post_text = post.title
        
    # Generate tweet text using the Reddit client's helper method
    if metadata:
        post_text = reddit_client.generate_tweet_title(metadata)
        
    # Try to post to Twitter
    tweet_result = None
    
    try:
        if content_type == "video":
            # Post video to Twitter
            tweet_result = twitter_client.post_video(downloaded_path, post_text)
            logger.info(f"Posted video {submission.id} to Twitter")
        
        elif content_type == "image":
            # Post image to Twitter
            tweet_result = twitter_client.post_image(downloaded_path, post_text)
            logger.info(f"Posted image {submission.id} to Twitter")
            
        elif content_type == "gallery":
            # Check how many images we have in the gallery
            if len(gallery_image_paths) > 1:
                # Create a thread if we have multiple images
                logger.info(f"Posting gallery with {len(gallery_image_paths)} images as a Twitter thread")
                
                # Create tweet texts for the thread (first tweet uses main text)
                continue_texts = []
                for i in range(1, len(gallery_image_paths)):
                    # We no longer need to strip content type indicators since we don't add them anymore
                    base_text = post_text
                    
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
            return
        
    # Check if we got a valid tweet result
    if not tweet_result:
        post.error = True
        post.error_message = "Failed to get Twitter post result"
        post.processed_at = datetime.utcnow()
        db.session.add(post)
        db.session.commit()
        logger.error(f"No tweet result for {submission.id}")
        return
    
    # Update post with Twitter info
    post.posted_to_twitter = True
    post.twitter_post_id = tweet_result['tweet_id']
    post.twitter_post_url = tweet_result['tweet_url']
    post.processed_at = datetime.utcnow()
    
    db.session.add(post)
    db.session.commit()
    
    # We only want to post one item per run, so exit after first success
    return True

# Initialize scheduler jobs
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
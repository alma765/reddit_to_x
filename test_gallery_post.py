"""
Test script for posting a specific Reddit gallery post to Twitter as a thread.
This will test our new gallery-to-thread feature using a real gallery post.
"""

import logging
import os
from datetime import datetime

from app import db
from models import Post
from bot.reddit_client import RedditClient
from bot.twitter_client import TwitterClient
from bot.video_processor import VideoProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
reddit_client = RedditClient()
twitter_client = TwitterClient(use_mock=False)  # Will fall back to mock if authentication fails
video_processor = VideoProcessor()

def post_gallery(reddit_id="1ka65ks"):
    """
    Process and post a specific Reddit gallery post to Twitter as a thread.
    
    Args:
        reddit_id (str): Reddit post ID to process
    """
    logger.info(f"Processing Reddit gallery post with ID: {reddit_id}")
    
    # Check if we've already processed this post
    existing_post = db.session.query(Post).filter_by(reddit_id=reddit_id).first()
    if existing_post:
        if existing_post.posted_to_twitter:
            logger.info(f"Post {reddit_id} already posted to Twitter: {existing_post.twitter_post_url}")
            return
        else:
            # If it exists but wasn't successfully posted, delete it to try again
            logger.info(f"Found existing post record that wasn't posted, removing to retry")
            db.session.delete(existing_post)
            db.session.commit()
    
    try:
        # Fetch the Reddit submission
        submission = reddit_client.reddit.submission(id=reddit_id)
        
        # Verify it's a gallery post
        if not (hasattr(submission, 'is_gallery') and submission.is_gallery):
            logger.error(f"Post {reddit_id} is not a gallery post")
            return
        
        # Check how many images are in the gallery
        image_urls = reddit_client.get_gallery_image_urls(submission)
        logger.info(f"Gallery post has {len(image_urls)} images")
        
        # Create a new post record
        post = Post(
            reddit_id=submission.id,
            reddit_url=submission.url,
            title=submission.title,
            subreddit=submission.subreddit.display_name,
            author=submission.author.name if submission.author else "[deleted]",
            content_type="gallery",
            created_at=datetime.utcnow()
        )
        
        # Generate a base filename for gallery images
        base_image_path = video_processor.generate_filename(submission.id, extension="")
        
        # Download all gallery images
        gallery_image_paths = reddit_client.download_gallery_images(submission, base_image_path)
        
        if not gallery_image_paths:
            logger.error(f"Failed to download gallery images for {submission.id}")
            post.error = True
            post.error_message = "Failed to download gallery images"
            db.session.add(post)
            db.session.commit()
            return
        
        # Store the path to the first image in the post record
        post.image_path = gallery_image_paths[0]
        post.image_size_bytes = os.path.getsize(gallery_image_paths[0])
        
        # Extract metadata and generate a clean, tweet-friendly title
        post_metadata = reddit_client.extract_post_metadata(submission)
        
        # Store the cleaned title in our database
        post.cleaned_title = post_metadata['cleaned_title']
        
        # Use the tweet-friendly title
        post_text = post_metadata['tweet_title']
        
        # Make sure we don't exceed Twitter's character limit
        if len(post_text) > 280:
            max_length = 280 - 3  # Room for ellipsis
            post_text = post_text[:max_length] + "..."
        
        logger.info(f"Using tweet text: {post_text}")
        
        # If we have multiple images, create a thread
        if len(gallery_image_paths) > 1:
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
            
            if thread_result.get('success'):
                tweet_result = {
                    'tweet_id': thread_result['first_tweet_id'],
                    'tweet_url': thread_result['first_tweet_url']
                }
                logger.info(f"Successfully posted gallery thread with {len(gallery_image_paths)} images from {submission.id} to Twitter")
            else:
                # If thread creation failed, log error and return
                logger.error(f"Failed to create Twitter thread for gallery {submission.id}")
                post.error = True
                post.error_message = f"Failed to create Twitter thread: {thread_result.get('error', 'Unknown error')}"
                db.session.add(post)
                db.session.commit()
                return
        else:
            # If there's only one image, post normally
            tweet_result = twitter_client.post_image(gallery_image_paths[0], post_text)
            logger.info(f"Posted single image from gallery {submission.id} to Twitter")
        
        # Update post with Twitter info
        post.posted_to_twitter = True
        post.twitter_post_id = tweet_result['tweet_id']
        post.twitter_post_url = tweet_result['tweet_url']
        post.processed_at = datetime.utcnow()
        
        db.session.add(post)
        db.session.commit()
        
        logger.info(f"Successfully processed gallery post {submission.id}. Posted to Twitter: {post.twitter_post_url}")
        
    except Exception as e:
        logger.exception(f"Error processing gallery post {reddit_id}: {str(e)}")
        if 'post' in locals():
            post.error = True
            post.error_message = str(e)
            db.session.add(post)
            db.session.commit()

if __name__ == "__main__":
    # Import the app to create an application context
    from app import app
    
    # Run within a Flask application context
    with app.app_context():
        # First delete any existing record of this post to force a repost
        existing_post = db.session.query(Post).filter_by(reddit_id="1ka65ks").first()
        if existing_post:
            logger.info(f"Deleting existing post record for 1ka65ks to force repost")
            db.session.delete(existing_post)
            db.session.commit()
        
        # Process the Vietnam War gallery post (ID: 1ka65ks)
        post_gallery("1ka65ks")
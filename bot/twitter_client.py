import logging
import os
import tweepy
from datetime import datetime

from config import (
    TWITTER_API_KEY,
    TWITTER_API_KEY_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET
)

logger = logging.getLogger(__name__)

class TwitterClient:
    def __init__(self):
        """Initialize Twitter API client using Tweepy"""        
        if not all([TWITTER_API_KEY, TWITTER_API_KEY_SECRET, 
                   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
            error_msg = "Twitter API credentials are missing"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("Initializing Twitter client with OAuth 1.0a...")
        logger.debug(f"API Key: {TWITTER_API_KEY[:4]}...{TWITTER_API_KEY[-4:] if len(TWITTER_API_KEY) > 8 else ''}")
        logger.debug(f"Access Token: {TWITTER_ACCESS_TOKEN[:4]}...{TWITTER_ACCESS_TOKEN[-4:] if len(TWITTER_ACCESS_TOKEN) > 8 else ''}")
        
        # Auth v1.1 (needed for media upload)
        # Per X.com documentation, v1.1 endpoints are authenticated using OAuth 1.0a
        self.auth = tweepy.OAuth1UserHandler(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
            callback=None
        )
        
        # Initialize API v1.1 client
        self.api = tweepy.API(self.auth)
        
        # API v2 client - also using OAuth1 credentials 
        self.client = tweepy.Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
        )
        
        # Test connection
        try:
            # Test API v1.1 connection
            logger.info("Testing Twitter API v1.1 connection...")
            user = self.api.verify_credentials()
            logger.info(f"Twitter client initialized - authenticated as @{user.screen_name}")
            
            # Test API v2 connection
            logger.info("Testing Twitter API v2 connection...")
            me = self.client.get_me()
            if me.data:
                logger.info(f"Twitter API v2 connection successful - user ID: {me.data.id}")
            
            logger.info(f"Twitter API connection successful - app is authorized for this account")
        except tweepy.TweepyException as e:
            error_msg = str(e)
            logger.error(f"Twitter authentication failed: {error_msg}")
            
            # Log more detailed error information
            if "401" in error_msg:
                logger.error("Error 401: Unauthorized - Your credentials may be invalid or expired")
                logger.error("Make sure you have:") 
                logger.error("1. Correct API key and secret")
                logger.error("2. Correct access token and secret with appropriate permissions")
                logger.error("3. The API key and access token match the same application")
                logger.error("4. Your app has the appropriate Twitter API access level")
            elif "403" in error_msg:
                logger.error("Error 403: Forbidden - Your app lacks proper permissions")
                logger.error("Make sure your Twitter app has read/write permissions")
            elif "429" in error_msg or "Too Many Requests" in error_msg:
                # Try to extract the reset time from the response headers if available
                reset_time = None
                
                # Check if we have access to the response object through the exception
                if hasattr(e, 'response') and e.response is not None:
                    reset_time = e.response.headers.get('x-rate-limit-reset')
                
                if reset_time:
                    import datetime
                    # Convert Unix timestamp to datetime
                    reset_datetime = datetime.datetime.fromtimestamp(int(reset_time))
                    now = datetime.datetime.now()
                    minutes_remaining = max(0, int((reset_datetime - now).total_seconds() / 60))
                    
                    logger.error(f"Error 429: Rate limit exceeded - Will reset at {reset_datetime.isoformat()} (in {minutes_remaining} minutes)")
                else:
                    logger.error("Error 429: Rate limit exceeded - Will retry in 60 minutes")
                
            # Propagate the exception to the caller
            raise
        
    def is_rate_limited(self):
        """
        Check if the Twitter API is currently rate limited
        
        Returns:
            bool or tuple: False if not rate limited, or (True, reset_time) if rate limited
        """
        try:
            # Test API v2 connection
            me = self.client.get_me()
            return False  # If we get here, we're not rate limited
        except tweepy.TweepyException as e:
            error_msg = str(e)
            if "429" in error_msg or "Too Many Requests" in error_msg:
                logger.error("Twitter API is rate limited")
                
                # Try to extract the reset time from the response headers if available
                reset_time = None
                
                # Check if we have access to the response object through the exception
                if hasattr(e, 'response') and e.response is not None:
                    reset_time = e.response.headers.get('x-rate-limit-reset')
                
                if reset_time:
                    import datetime
                    # Convert Unix timestamp to datetime
                    reset_datetime = datetime.datetime.fromtimestamp(int(reset_time))
                    logger.error(f"Rate limit will reset at: {reset_datetime.isoformat()}")
                    return True, reset_datetime.isoformat()
                
                # Default 60-minute timeout if we can't get actual reset time
                import datetime
                default_reset = (datetime.datetime.now() + datetime.timedelta(hours=1)).isoformat()
                return True, default_reset
                
            # Other errors are not rate limit related
            return False
        
    def post_video(self, video_path, text=None):
        """
        Post a video to Twitter
        
        Args:
            video_path (str): Path to the video file
            text (str): Text to accompany the post
            
        Returns:
            dict: Response from Twitter API containing post ID and URL
            
        Raises:
            FileNotFoundError: If the video file doesn't exist
            tweepy.TweepyException: If there's an error posting to Twitter
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # First check if we're rate limited
        if self.is_rate_limited():
            error_msg = "Twitter rate limit reached! Will retry in 60 minutes"
            logger.error(error_msg)
            raise tweepy.TweepyException(error_msg)
        
        # First test that we can connect to the Twitter API
        logger.info("Testing Twitter API connection...")
        user = self.api.verify_credentials()
        logger.info(f"Authenticated as: @{user.screen_name}")
                
        # Upload the video using v1.1 API
        # Following X.com documentation on media uploads
        # https://docs.x.com/resources/media/upload-media
        
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        logger.info(f"Uploading video: {video_path} (size: {file_size_mb:.2f} MB)")
        
        # Use chunked upload for larger videos
        # This is required for videos > 5MB
        if file_size_mb > 5:
            logger.info("Using chunked upload for video > 5MB")
            
            # Tweepy handles chunked uploads automatically when using media_upload 
            # with a large file and appropriate category
            media = self.api.media_upload(
                filename=video_path,
                media_category='tweet_video',
                chunked=True
            )
        else:
            logger.info("Using standard upload for video < 5MB")
            media = self.api.media_upload(
                filename=video_path,
                media_category='tweet_video'
            )
        
        # Wait for media processing to complete
        media_id = media.media_id_string
        logger.info(f"Media uploaded with ID: {media_id}, waiting for processing...")
        
        # Check if media is ready (chunked upload can take time to process)
        self._wait_for_media_processing(media_id)
        
        # Create the tweet with media using v2 API
        tweet_text = text or "Combat footage from Reddit r/CombatFootage"
        logger.info(f"Posting tweet with text: {tweet_text[:50]}...")
        
        response = self.client.create_tweet(
            text=tweet_text[:280],  # Ensure text fits within Twitter limit
            media_ids=[media_id]
        )
        
        tweet_id = response.data['id']
        tweet_url = f"https://x.com/WCorrespon25294/status/{tweet_id}"
        
        logger.info(f"Video posted to Twitter: {tweet_url}")
        
        return {
            'tweet_id': tweet_id,
            'tweet_url': tweet_url
        }
    
    def post_image(self, image_path, text=None, reply_to_id=None):
        """
        Post an image to Twitter
        
        Args:
            image_path (str): Path to the image file
            text (str): Text to accompany the post
            reply_to_id (str): Optional tweet ID to reply to (for creating threads)
            
        Returns:
            dict: Response from Twitter API containing post ID and URL
            
        Raises:
            FileNotFoundError: If the image file doesn't exist
            tweepy.TweepyException: If there's an error posting to Twitter
        """
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # First check if we're rate limited
        if self.is_rate_limited():
            error_msg = "Twitter rate limit reached! Will retry in 60 minutes"
            logger.error(error_msg)
            raise tweepy.TweepyException(error_msg)
        
        # First test that we can connect to the Twitter API
        logger.info("Testing Twitter API connection...")
        user = self.api.verify_credentials()
        logger.info(f"Authenticated as: @{user.screen_name}")
                
        # Upload the image using v1.1 API
        file_size_kb = os.path.getsize(image_path) / 1024
        logger.info(f"Uploading image: {image_path} (size: {file_size_kb:.2f} KB)")
        
        media = self.api.media_upload(
            filename=image_path,
            media_category='tweet_image'
        )
            
        # Image uploads are usually processed immediately, but just in case
        media_id = media.media_id_string
        logger.info(f"Image uploaded with ID: {media_id}")
        
        # Create the tweet with media using v2 API
        tweet_text = text or "Image from Reddit"
        logger.info(f"Posting tweet with text: {tweet_text[:50]}...")
        
        # Handle reply if needed
        if reply_to_id:
            logger.info(f"Posting as reply to tweet ID: {reply_to_id}")
            response = self.client.create_tweet(
                text=tweet_text[:280],  # Ensure text fits within Twitter limit
                media_ids=[media_id],
                in_reply_to_tweet_id=reply_to_id
            )
        else:
            response = self.client.create_tweet(
                text=tweet_text[:280],  # Ensure text fits within Twitter limit
                media_ids=[media_id]
            )
        
        tweet_id = response.data['id']
        tweet_url = f"https://x.com/WCorrespon25294/status/{tweet_id}"
        
        logger.info(f"Image posted to Twitter: {tweet_url}")
        
        return {
            'tweet_id': tweet_id,
            'tweet_url': tweet_url
        }
            
    def create_thread_with_images(self, image_paths, main_text=None, continue_texts=None):
        """
        Create a Twitter thread with multiple images
        
        Args:
            image_paths (list): List of paths to image files
            main_text (str): Text for the first tweet
            continue_texts (list): Optional list of texts for continuation tweets
            
        Returns:
            dict: Information about the created thread including all tweet IDs and URLs
            
        Raises:
            ValueError: If no images are provided
            tweepy.TweepyException: If there's an error posting to Twitter
        """
        if not image_paths:
            error_msg = "No images provided for thread creation"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # First check if we're rate limited
        if self.is_rate_limited():
            error_msg = "Twitter rate limit reached! Will retry in 60 minutes"
            logger.error(error_msg)
            raise tweepy.TweepyException(error_msg)
            
        # Create the first tweet with the first image
        first_tweet = self.post_image(image_paths[0], main_text)
        
        thread_tweets = [first_tweet]
        parent_id = first_tweet['tweet_id']
        
        # If we have more images, create reply tweets
        for i, image_path in enumerate(image_paths[1:]):
            # Get text for this continuation, if provided
            text = None
            if continue_texts and i < len(continue_texts):
                text = continue_texts[i]
            else:
                # Default continuation text
                text = f"Continued ({i+2}/{len(image_paths)})"
                
            # Post as reply to previous tweet
            try:
                reply_tweet = self.post_image(image_path, text, reply_to_id=parent_id)
                thread_tweets.append(reply_tweet)
                
                # Update parent for next tweet in thread
                parent_id = reply_tweet['tweet_id']
            except Exception as e:
                logger.error(f"Error creating thread at image {i+2}: {str(e)}")
                # Propagate the exception to stop the thread creation
                raise
        
        logger.info(f"Created thread with {len(thread_tweets)} tweets")
        
        return {
            'success': True,
            'tweets': thread_tweets,
            'first_tweet_id': first_tweet['tweet_id'],
            'first_tweet_url': first_tweet['tweet_url']
        }

    def _wait_for_media_processing(self, media_id):
        """
        Wait for media processing to complete on Twitter
        
        Args:
            media_id (str): ID of the media to check
        """
        from time import sleep
        
        media_info = self.api.get_media_upload_status(media_id=media_id)
        
        while media_info.processing_info and media_info.processing_info['state'] in ['pending', 'in_progress']:
            logger.debug(f"Media processing status: {media_info.processing_info['state']}")
            
            wait_time = media_info.processing_info.get('check_after_secs', 5)
            sleep(wait_time)
            
            media_info = self.api.get_media_upload_status(media_id=media_id)
        
        # Check for processing errors
        if (media_info.processing_info and 
            media_info.processing_info['state'] == 'failed'):
            error = media_info.processing_info.get('error', {})
            logger.error(f"Media processing failed: {error}")
            raise Exception(f"Twitter media processing failed: {error}")
            
        logger.info(f"Media processing complete for media_id: {media_id}")

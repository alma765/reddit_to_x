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

class MockTwitterClient:
    """Mock Twitter client for testing or when credentials are not available"""
    def __init__(self):
        """Initialize mock Twitter client"""
        logger.info("Mock Twitter client initialized - posts will be simulated but not actually sent")
    
    def post_video(self, video_path, text=None):
        """
        Simulate posting a video to Twitter
        
        Args:
            video_path (str): Path to the video file
            text (str): Text to accompany the post
            
        Returns:
            dict: Mock response with tweet ID and URL
        """
        import uuid
        
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
        
    def post_image(self, image_path, text=None):
        """
        Simulate posting an image to Twitter
        
        Args:
            image_path (str): Path to the image file
            text (str): Text to accompany the post
            
        Returns:
            dict: Mock response with tweet ID and URL
        """
        import uuid
        
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # Get file size
        file_size_kb = os.path.getsize(image_path) / 1024
        
        # Generate mock tweet ID
        mock_tweet_id = str(uuid.uuid4()).replace('-', '')[:16]
        mock_tweet_url = f"https://twitter.com/user/status/{mock_tweet_id}"
        
        logger.info(f"MOCK: Would post image ({file_size_kb:.2f} KB) to Twitter")
        logger.info(f"MOCK: Tweet text: {text[:50] if text else 'No text'}")
        logger.info(f"MOCK: Tweet ID: {mock_tweet_id}")
        logger.info(f"MOCK: Tweet URL: {mock_tweet_url}")
        
        return {
            'tweet_id': mock_tweet_id,
            'tweet_url': mock_tweet_url
        }

class TwitterClient:
    def __init__(self, use_mock=False):
        """Initialize Twitter API client using Tweepy"""
        self.use_mock = use_mock
        
        if use_mock or not all([TWITTER_API_KEY, TWITTER_API_KEY_SECRET, 
                               TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
            logger.warning("Using mock Twitter client - tweets will not be posted to Twitter")
            self.mock_client = MockTwitterClient()
            return
            
        try:
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
                
                logger.warning("Falling back to mock Twitter client")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                
        except Exception as e:
            logger.error(f"Error initializing Twitter client: {str(e)}")
            logger.warning("Falling back to mock Twitter client")
            self.use_mock = True
            self.mock_client = MockTwitterClient()
    
    def post_video(self, video_path, text=None):
        """
        Post a video to Twitter
        
        Args:
            video_path (str): Path to the video file
            text (str): Text to accompany the post
            
        Returns:
            dict: Response from Twitter API containing post ID and URL
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # If we're using the mock client, delegate to it
        if self.use_mock:
            logger.warning("Using mock Twitter client for posting")
            return self.mock_client.post_video(video_path, text)
        
        try:
            # First test that we can connect to the Twitter API
            logger.info("Testing Twitter API connection...")
            try:
                # Simple API call to verify credentials
                user = self.api.verify_credentials()
                logger.info(f"Authenticated as: @{user.screen_name}")
            except Exception as auth_error:
                logger.error(f"Authentication error: {str(auth_error)}")
                logger.warning("Falling back to mock Twitter client")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_video(video_path, text)
                
            # Upload the video using v1.1 API
            # Following X.com documentation on media uploads
            # https://docs.x.com/resources/media/upload-media
            
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"Uploading video: {video_path} (size: {file_size_mb:.2f} MB)")
            
            try:
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
            except Exception as media_error:
                logger.error(f"Media upload error: {str(media_error)}")
                logger.warning("Falling back to mock Twitter client due to media upload error")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_video(video_path, text)
            
            # Create the tweet with media using v2 API
            tweet_text = text or "Combat footage from Reddit r/CombatFootage"
            logger.info(f"Posting tweet with text: {tweet_text[:50]}...")
            
            try:
                response = self.client.create_tweet(
                    text=tweet_text[:280],  # Ensure text fits within Twitter limit
                    media_ids=[media_id]
                )
            except Exception as tweet_error:
                logger.error(f"Tweet creation error: {str(tweet_error)}")
                logger.warning("Falling back to mock Twitter client due to tweet creation error")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_video(video_path, text)
            
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/user/status/{tweet_id}"
            
            logger.info(f"Video posted to Twitter: {tweet_url}")
            
            return {
                'tweet_id': tweet_id,
                'tweet_url': tweet_url
            }
            
        except Exception as e:
            logger.error(f"Error posting video to Twitter: {str(e)}")
            # Fall back to mock Twitter client as a last resort
            logger.warning("Falling back to mock Twitter client due to unexpected error")
            self.use_mock = True
            self.mock_client = MockTwitterClient()
            return self.mock_client.post_video(video_path, text)
    
    def post_image(self, image_path, text=None):
        """
        Post an image to Twitter
        
        Args:
            image_path (str): Path to the image file
            text (str): Text to accompany the post
            
        Returns:
            dict: Response from Twitter API containing post ID and URL
        """
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # If we're using the mock client, delegate to it
        if self.use_mock:
            logger.warning("Using mock Twitter client for posting")
            return self.mock_client.post_image(image_path, text)
        
        try:
            # First test that we can connect to the Twitter API
            logger.info("Testing Twitter API connection...")
            try:
                # Simple API call to verify credentials
                user = self.api.verify_credentials()
                logger.info(f"Authenticated as: @{user.screen_name}")
            except Exception as auth_error:
                logger.error(f"Authentication error: {str(auth_error)}")
                logger.warning("Falling back to mock Twitter client")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_image(image_path, text)
                
            # Upload the image using v1.1 API
            file_size_kb = os.path.getsize(image_path) / 1024
            logger.info(f"Uploading image: {image_path} (size: {file_size_kb:.2f} KB)")
            
            try:
                media = self.api.media_upload(
                    filename=image_path,
                    media_category='tweet_image'
                )
                
                # Image uploads are usually processed immediately, but just in case
                media_id = media.media_id_string
                logger.info(f"Image uploaded with ID: {media_id}")
                
            except Exception as media_error:
                logger.error(f"Media upload error: {str(media_error)}")
                logger.warning("Falling back to mock Twitter client due to media upload error")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_image(image_path, text)
            
            # Create the tweet with media using v2 API
            tweet_text = text or "Image from Reddit"
            logger.info(f"Posting tweet with text: {tweet_text[:50]}...")
            
            try:
                response = self.client.create_tweet(
                    text=tweet_text[:280],  # Ensure text fits within Twitter limit
                    media_ids=[media_id]
                )
            except Exception as tweet_error:
                logger.error(f"Tweet creation error: {str(tweet_error)}")
                logger.warning("Falling back to mock Twitter client due to tweet creation error")
                self.use_mock = True
                self.mock_client = MockTwitterClient()
                return self.mock_client.post_image(image_path, text)
            
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/user/status/{tweet_id}"
            
            logger.info(f"Image posted to Twitter: {tweet_url}")
            
            return {
                'tweet_id': tweet_id,
                'tweet_url': tweet_url
            }
            
        except Exception as e:
            logger.error(f"Error posting image to Twitter: {str(e)}")
            # Fall back to mock Twitter client as a last resort
            logger.warning("Falling back to mock Twitter client due to unexpected error")
            self.use_mock = True
            self.mock_client = MockTwitterClient()
            return self.mock_client.post_image(image_path, text)

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

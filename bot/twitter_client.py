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
            logger.error("Twitter API credentials not configured")
            raise ValueError("Twitter API credentials not configured")
        
        # Auth v1.1 (needed for media upload)
        self.auth = tweepy.OAuth1UserHandler(
            TWITTER_API_KEY,
            TWITTER_API_KEY_SECRET,
            TWITTER_ACCESS_TOKEN,
            TWITTER_ACCESS_TOKEN_SECRET
        )
        self.api = tweepy.API(self.auth)
        
        # API v2 client - using OAuth1 credentials (bearer token not required)
        # Print key info for debugging (safely)
        logger.debug(f"API Key: {TWITTER_API_KEY[:4]}...{TWITTER_API_KEY[-4:] if len(TWITTER_API_KEY) > 8 else ''}")
        logger.debug(f"Access Token: {TWITTER_ACCESS_TOKEN[:4]}...{TWITTER_ACCESS_TOKEN[-4:] if len(TWITTER_ACCESS_TOKEN) > 8 else ''}")
        
        self.client = tweepy.Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
        )
        
        logger.info("Twitter client initialized")
    
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
        
        try:
            # First test that we can connect to the Twitter API
            logger.info("Testing Twitter API connection...")
            try:
                # Simple API call to verify credentials
                user = self.api.verify_credentials()
                logger.info(f"Authenticated as: @{user.screen_name}")
            except Exception as auth_error:
                logger.error(f"Authentication error: {str(auth_error)}")
                raise Exception(f"Twitter API authentication failed: {str(auth_error)}")
                
            # Upload the video using v1.1 API
            logger.info(f"Uploading video: {video_path} (size: {os.path.getsize(video_path)/1024/1024:.2f} MB)")
            
            try:
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
                raise Exception(f"Twitter media upload failed: {str(media_error)}")
            
            # Create the tweet with media using v2 API
            tweet_text = text or "Check out this video from Reddit!"
            logger.info(f"Posting tweet with text: {tweet_text[:50]}...")
            
            try:
                response = self.client.create_tweet(
                    text=tweet_text[:280],  # Ensure text fits within Twitter limit
                    media_ids=[media_id]
                )
            except Exception as tweet_error:
                logger.error(f"Tweet creation error: {str(tweet_error)}")
                raise Exception(f"Twitter tweet creation failed: {str(tweet_error)}")
            
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/user/status/{tweet_id}"
            
            logger.info(f"Video posted to Twitter: {tweet_url}")
            
            return {
                'tweet_id': tweet_id,
                'tweet_url': tweet_url
            }
            
        except Exception as e:
            logger.error(f"Error posting video to Twitter: {str(e)}")
            raise
    
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

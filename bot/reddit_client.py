import logging
import praw
import requests
import os
import re
from datetime import datetime
from urllib.parse import urlparse

from config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_USERNAME,
    REDDIT_PASSWORD,
    SUBREDDITS,
    POSTS_LIMIT
)

logger = logging.getLogger(__name__)

class RedditClient:
    def __init__(self):
        """Initialize Reddit API client using PRAW"""
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            logger.error("Reddit API credentials not configured")
            raise ValueError("Reddit API credentials not configured")
        
        self.reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD
        )
        logger.info(f"Reddit client initialized for subreddits: {', '.join(SUBREDDITS)}")
    
    def fetch_videos(self, subreddits=None, limit=None):
        """
        Fetch video posts from specified subreddits
        
        Args:
            subreddits (list): List of subreddit names to fetch from
            limit (int): Number of posts to fetch per subreddit
            
        Returns:
            list: List of submission objects containing videos
        """
        if subreddits is None:
            subreddits = SUBREDDITS
        
        if limit is None:
            limit = POSTS_LIMIT
            
        logger.info(f"Fetching videos from {', '.join(subreddits)}")
        
        video_posts = []
        
        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                
                # Fetch hot posts from the subreddit
                for submission in subreddit.hot(limit=limit):
                    if self._has_video(submission):
                        video_posts.append(submission)
                        logger.debug(f"Found video: {submission.title} in r/{subreddit_name}")
                
            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {str(e)}")
        
        logger.info(f"Found {len(video_posts)} video posts across all subreddits")
        return video_posts

    def _has_video(self, submission):
        """
        Check if a submission has a video attached
        
        Args:
            submission: Reddit submission object
            
        Returns:
            bool: True if submission has a video, False otherwise
        """
        # Check for Reddit's native video
        if hasattr(submission, 'is_video') and submission.is_video:
            return True
        
        # Check for media in the submission
        if hasattr(submission, 'media') and submission.media:
            if 'reddit_video' in submission.media:
                return True
                
            # Check for other video providers
            if 'type' in submission.media and 'video' in submission.media['type']:
                return True
        
        # Check common video URLs in the submission URL
        url = submission.url.lower()
        video_domains = ['gfycat.com', 'youtube.com', 'youtu.be', 'vimeo.com', 'streamable.com']
        video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.gifv']
        
        # Check if URL is from a known video domain
        parsed_url = urlparse(url)
        if any(domain in parsed_url.netloc for domain in video_domains):
            return True
            
        # Check if URL ends with a video extension
        if any(url.endswith(ext) for ext in video_extensions):
            return True
            
        # Check for Imgur direct video/gif links
        if 'imgur.com' in url and (any(ext in url for ext in video_extensions) or '/a/' not in url):
            return True
        
        return False
    
    def get_video_url(self, submission):
        """
        Extract the direct video URL from a Reddit submission
        
        Args:
            submission: Reddit submission object
            
        Returns:
            str: Direct URL to the video or None if not found
        """
        if hasattr(submission, 'is_video') and submission.is_video:
            # Reddit hosted video
            if hasattr(submission, 'media') and submission.media and 'reddit_video' in submission.media:
                return submission.media['reddit_video']['fallback_url']
        
        # For gfycat links
        if 'gfycat.com' in submission.url:
            gfycat_id = re.search(r'gfycat\.com\/(?:detail\/)?(\w+)', submission.url)
            if gfycat_id:
                return f"https://giant.gfycat.com/{gfycat_id.group(1)}.mp4"
        
        # For Imgur .gifv, convert to .mp4
        if submission.url.endswith('.gifv') and 'imgur.com' in submission.url:
            return submission.url.replace('.gifv', '.mp4')
        
        # If it's already a direct video link, return it
        if any(submission.url.endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
            return submission.url
        
        # For YouTube, we would need a separate downloader
        # This is left for you to implement using youtube-dl or similar library
        
        # Fallback: try the URL as is
        return submission.url

    def download_video(self, video_url, download_path):
        """
        Download a video from a URL to the specified path
        
        Args:
            video_url (str): URL of the video to download
            download_path (str): Path where the video should be saved
            
        Returns:
            str: Path to the downloaded video or None if download failed
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            
            # First, check the total file size
            response = requests.head(video_url, allow_redirects=True)
            if 'Content-Length' in response.headers:
                size_bytes = int(response.headers['Content-Length'])
                size_mb = size_bytes / (1024 * 1024)
                
                # Log file size
                logger.info(f"Video size: {size_mb:.2f} MB for {video_url}")
                
                # If size is greater than 100MB, don't even try to download
                # We use 100MB as a hard limit since compression might not work well above this
                if size_mb > 100:
                    logger.warning(f"Video is too large ({size_mb:.2f} MB > 100 MB) - skipping")
                    return None
            
            # Download the video
            download_response = requests.get(video_url, stream=True)
            download_response.raise_for_status()
            
            # Save the video to the specified path
            file_size = 0
            with open(download_path, 'wb') as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    file_size += len(chunk)
                    f.write(chunk)
                    
                    # If we've downloaded more than 100MB, abort
                    if file_size > 100 * 1024 * 1024:  # 100MB in bytes
                        logger.warning(f"Download aborted - file exceeds 100MB")
                        f.close()
                        os.remove(download_path)
                        return None
            
            # Check the final size
            final_size_mb = os.path.getsize(download_path) / (1024 * 1024)
            logger.info(f"Downloaded video to {download_path} (Size: {final_size_mb:.2f} MB)")
            return download_path
            
        except Exception as e:
            logger.error(f"Error downloading video from {video_url}: {str(e)}")
            if os.path.exists(download_path):
                try:
                    os.remove(download_path)
                except:
                    pass
            return None

import logging
import praw
import requests
import os
import re
import html
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
                submission_count = 0
                for submission in subreddit.hot(limit=limit):
                    submission_count += 1
                    logger.info(f"Checking submission: {submission.id} - {submission.title}")
                    
                    has_video = self._has_video(submission)
                    if has_video:
                        logger.info(f"Found video: {submission.title} in r/{subreddit_name}")
                        video_posts.append(submission)
                    else:
                        logger.info(f"No video found in submission: {submission.id}")
                
                logger.info(f"Checked {submission_count} submissions, found {len(video_posts)} videos")
                
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
    
    def extract_post_metadata(self, submission):
        """
        Extract useful metadata from a Reddit submission, including cleaned title
        
        Args:
            submission: Reddit submission object
            
        Returns:
            dict: Dictionary containing post metadata
        """
        # Get basic submission info
        metadata = {
            'reddit_id': submission.id,
            'title': submission.title,
            'cleaned_title': self.clean_title(submission.title),
            'author': submission.author.name if submission.author else '[deleted]',
            'subreddit': submission.subreddit.display_name,
            'score': submission.score,
            'upvote_ratio': submission.upvote_ratio,
            'created_utc': submission.created_utc,
            'permalink': submission.permalink,
            'url': submission.url,
            'num_comments': submission.num_comments,
            'is_nsfw': submission.over_18,
            'is_original_content': submission.is_original_content if hasattr(submission, 'is_original_content') else False,
        }
        
        # Extract flair information if available
        if hasattr(submission, 'link_flair_text') and submission.link_flair_text:
            metadata['flair'] = submission.link_flair_text
        else:
            metadata['flair'] = None
            
        # Get post content if it's a self post
        if hasattr(submission, 'selftext') and submission.selftext:
            metadata['selftext'] = submission.selftext
        else:
            metadata['selftext'] = None
            
        # Check for [OC] tag in title
        metadata['has_oc_tag'] = '[OC]' in submission.title or '(OC)' in submission.title
        
        # Generate a tweet-friendly title (will be truncated later if needed)
        metadata['tweet_title'] = self.generate_tweet_title(metadata)
        
        logger.info(f"Extracted metadata for post {submission.id}: {metadata['cleaned_title']}")
        return metadata
    
    def clean_title(self, title):
        """
        Clean a Reddit title for better readability
        
        Args:
            title (str): Original Reddit post title
            
        Returns:
            str: Cleaned title
        """
        # Decode HTML entities
        title = html.unescape(title)
        
        # Remove Reddit-specific formatting
        title = re.sub(r'\[.+?\]|\(.+?\)', '', title)  # Remove content in [] and ()
        title = re.sub(r'\s+', ' ', title)  # Normalize spaces
        
        # Remove common fluff phrases
        fluff_phrases = [
            'just', 'so', 'actually', 'literally', 'basically',
            'I think', 'In my opinion', 'IMO', 'IMHO', 
            'upvote', 'downvote', 'karma', 'reddit',
            'cake day', 'cakeday', 'my first post', 'first time',
            'Title', 'title says it all', 'Don\'t know if posted before',
            'Not sure if this belongs here', 'Not sure if repost'
        ]
        
        for phrase in fluff_phrases:
            title = re.sub(r'\b' + re.escape(phrase) + r'\b', '', title, flags=re.IGNORECASE)
        
        # Clean up any remaining artifacts
        title = re.sub(r'\s+', ' ', title)  # Remove multiple spaces
        title = re.sub(r'^\s+|\s+$', '', title)  # Trim whitespace
        
        # Remove excessive punctuation at the end
        title = re.sub(r'[.,!?:;-]+$', '', title)
        
        # If title is empty after cleaning, return original
        if not title.strip():
            return title
            
        return title
    
    def generate_tweet_title(self, metadata):
        """
        Generate a title suitable for Twitter
        
        Args:
            metadata (dict): Post metadata from extract_post_metadata
            
        Returns:
            str: Twitter-friendly title
        """
        # Use cleaned title as the base
        title = metadata['cleaned_title'] or metadata['title']
        
        # Add location/date information if found in title
        location_match = re.search(r'in\s+([A-Za-z\s]+)(?:,\s+([A-Za-z\s]+))?', title)
        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})|(\d{1,2}/\d{1,2}/\d{2,4})', title)
        
        tweet = title
        
        # Add flair if relevant
        if metadata['flair'] and metadata['flair'].lower() not in ['video', 'media', 'post']:
            tweet += f" [{metadata['flair']}]"
        
        return tweet

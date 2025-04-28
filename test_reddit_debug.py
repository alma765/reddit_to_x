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

# Import directly
import praw
from urllib.parse import urlparse
import re

def debug_reddit_api():
    """Debug Reddit API connection and post detection"""
    try:
        # Import credentials
        from config import (
            REDDIT_CLIENT_ID,
            REDDIT_CLIENT_SECRET,
            REDDIT_USER_AGENT,
            REDDIT_USERNAME,
            REDDIT_PASSWORD
        )
        
        logger.info("Initializing Reddit client")
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD
        )
        
        # Make sure we're logged in
        logger.info(f"Authenticated as: {reddit.user.me()}")
        
        # Get a specific subreddit
        subreddit_name = 'CombatFootage'
        logger.info(f"Fetching from r/{subreddit_name}")
        subreddit = reddit.subreddit(subreddit_name)
        
        # Get hot posts
        submission_count = 0
        video_posts = []
        for submission in subreddit.hot(limit=10):
            submission_count += 1
            logger.info(f"\nSubmission {submission_count}: {submission.id} - {submission.title}")
            logger.info(f"  URL: {submission.url}")
            logger.info(f"  is_video attribute: {submission.is_video if hasattr(submission, 'is_video') else 'not present'}")
            
            # Check media attribute
            if hasattr(submission, 'media') and submission.media:
                logger.info(f"  Media: {submission.media.keys()}")
                if 'reddit_video' in submission.media:
                    logger.info(f"  Reddit video detected: {submission.media['reddit_video']}")
                    video_posts.append(submission)
                    continue
                    
                if 'type' in submission.media:
                    logger.info(f"  Media type: {submission.media['type']}")
                    if 'video' in submission.media['type']:
                        logger.info(f"  Video in media type detected")
                        video_posts.append(submission)
                        continue
            else:
                logger.info("  No media attribute or it's None")
            
            # Check URL for video domains
            url = submission.url.lower()
            video_domains = ['gfycat.com', 'youtube.com', 'youtu.be', 'vimeo.com', 'streamable.com']
            video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.gifv']
            
            parsed_url = urlparse(url)
            if any(domain in parsed_url.netloc for domain in video_domains):
                logger.info(f"  URL is from a video domain: {parsed_url.netloc}")
                video_posts.append(submission)
                continue
                
            if any(url.endswith(ext) for ext in video_extensions):
                logger.info(f"  URL has a video extension")
                video_posts.append(submission)
                continue
                
            if 'imgur.com' in url and (any(ext in url for ext in video_extensions) or '/a/' not in url):
                logger.info(f"  Imgur video/gif link detected")
                video_posts.append(submission)
                continue
            
            logger.info("  No video detected in this submission")
        
        logger.info(f"\nChecked {submission_count} submissions, found {len(video_posts)} videos")
        
        # Print details about found videos
        for i, submission in enumerate(video_posts, 1):
            logger.info(f"\nVideo {i}: {submission.id} - {submission.title}")
            logger.info(f"  URL: {submission.url}")
            
            # Try to extract direct video URL 
            direct_url = None
            if hasattr(submission, 'is_video') and submission.is_video:
                if hasattr(submission, 'media') and submission.media and 'reddit_video' in submission.media:
                    direct_url = submission.media['reddit_video']['fallback_url']
            
            # For gfycat links
            if 'gfycat.com' in submission.url:
                gfycat_id = re.search(r'gfycat\.com\/(?:detail\/)?(\w+)', submission.url)
                if gfycat_id:
                    direct_url = f"https://giant.gfycat.com/{gfycat_id.group(1)}.mp4"
            
            # For Imgur .gifv, convert to .mp4
            if submission.url.endswith('.gifv') and 'imgur.com' in submission.url:
                direct_url = submission.url.replace('.gifv', '.mp4')
            
            # If it's already a direct video link, return it
            if any(submission.url.endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
                direct_url = submission.url
            
            logger.info(f"  Direct video URL: {direct_url or 'Could not extract'}")
            
    except Exception as e:
        logger.exception(f"Error debugging Reddit API: {str(e)}")

if __name__ == "__main__":
    debug_reddit_api()
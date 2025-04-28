import os
import logging
import praw
import requests
from urllib.parse import urlparse
import sys
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reddit API credentials from environment
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = 'python:reddit-video-fetcher:v1.0'

def initialize_reddit_client():
    """Initialize the Reddit API client using PRAW"""
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.error("Reddit API credentials not configured")
        sys.exit(1)
    
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            check_for_async=False
        )
        logger.info("Reddit client initialized")
        return reddit
    except Exception as e:
        logger.error(f"Error initializing Reddit client: {e}")
        sys.exit(1)

def get_submission(reddit, url_or_id):
    """Get a Reddit submission from URL or ID"""
    try:
        if "reddit.com" in url_or_id:
            # Extract submission ID from URL
            parts = urlparse(url_or_id).path.rstrip('/').split('/')
            submission_id = next((p for p in parts if len(p) == 6 and p[0] == 't' or any(c.isalpha() and c.islower() for c in p) and any(c.isdigit() for c in p)), None)
            
            if not submission_id:
                # If we didn't find a typical submission ID, try getting the ID from comments URL format
                # Example: /r/subreddit/comments/abcdef/title/
                comments_index = parts.index('comments') if 'comments' in parts else -1
                if comments_index >= 0 and len(parts) > comments_index + 1:
                    submission_id = parts[comments_index + 1]
        else:
            submission_id = url_or_id
        
        logger.info(f"Getting submission with ID: {submission_id}")
        return reddit.submission(id=submission_id)
    except Exception as e:
        logger.error(f"Error getting submission: {e}")
        return None

def has_video(submission):
    """Check if a submission has a video attached"""
    if hasattr(submission, 'is_video') and submission.is_video:
        return True
    
    # Check for videos hosted on Reddit
    if hasattr(submission, 'media') and submission.media:
        if 'reddit_video' in submission.media:
            return True
    
    # Look for common video domains
    video_domains = [
        'v.redd.it', 'youtu.be', 'youtube.com', 
        'streamable.com', 'gfycat.com', 'vimeo.com'
    ]
    
    if any(domain in submission.url for domain in video_domains):
        return True
    
    return False

def get_video_url(submission):
    """Extract the direct video URL from a Reddit submission"""
    try:
        # Check for Reddit-hosted videos
        if hasattr(submission, 'media') and submission.media and 'reddit_video' in submission.media:
            return submission.media['reddit_video']['fallback_url']
        
        # Return the URL for other potential video sources
        return submission.url
    except Exception as e:
        logger.error(f"Error extracting video URL: {e}")
        return None

def download_video(video_url, output_file):
    """Download a video from a URL to the specified path"""
    try:
        # Create the downloads directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        response = requests.get(video_url, stream=True)
        response.raise_for_status()
        
        with open(output_file, 'wb') as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    out_file.write(chunk)
        
        logger.info(f"Video downloaded to {output_file}")
        return output_file
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

def extract_submission_info(submission):
    """Extract and return useful information about a submission"""
    info = {
        "id": submission.id,
        "title": submission.title,
        "author": submission.author.name if submission.author else "[deleted]",
        "subreddit": submission.subreddit.display_name,
        "score": submission.score,
        "upvote_ratio": submission.upvote_ratio,
        "url": submission.url,
        "permalink": f"https://reddit.com{submission.permalink}",
        "created_utc": submission.created_utc,
        "has_video": has_video(submission)
    }
    
    if info["has_video"]:
        info["video_url"] = get_video_url(submission)
    
    return info

def main():
    """Main function to test Reddit video fetching"""
    reddit = initialize_reddit_client()
    
    # Use command line argument if provided, otherwise use a default URL
    submission_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.reddit.com/r/CombatFootage/comments/1k8tcg7/ukrainian_fiber_optic_drone_operators_of_the_5th/"
    
    # Get the submission
    submission = get_submission(reddit, submission_url)
    if not submission:
        logger.error("Could not get submission")
        return
    
    # Log submission information
    info = extract_submission_info(submission)
    logger.info(f"Submission info:\n{json.dumps(info, indent=2)}")
    
    # Check if it has a video
    if not info["has_video"]:
        logger.error("Submission does not contain a video")
        return
    
    # Get the video URL
    video_url = info["video_url"]
    if not video_url:
        logger.error("Could not extract video URL")
        return
    
    # Download the video
    output_file = f"./downloads/{submission.id}.mp4"
    download_video(video_url, output_file)
    
    logger.info(f"Video processing complete for {submission.id}")

if __name__ == "__main__":
    main()
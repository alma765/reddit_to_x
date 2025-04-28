import os
import logging
import praw
import requests
import json
import time
from datetime import datetime
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = 'python:combat-footage-fetcher:v1.0'

# Configuration
SUBREDDIT = "CombatFootage"
DOWNLOAD_FOLDER = "./downloads"
MAX_POSTS = 25
MIN_SCORE = 10  # Minimum upvotes to consider
FETCH_PERIOD = "day"  # Can be "hour", "day", "week", "month", "year", "all"

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
        logger.info(f"Reddit client initialized for {SUBREDDIT}")
        return reddit
    except Exception as e:
        logger.error(f"Error initializing Reddit client: {e}")
        sys.exit(1)

def has_video(submission):
    """Check if a submission has a video attached"""
    # Check if the submission has the 'is_video' attribute set to True
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
            return submission.media['reddit_video']['fallback_url'].split('?')[0]
        
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
        file_size = os.path.getsize(output_file) / (1024 * 1024)  # Size in MB
        return {"path": output_file, "size_mb": file_size}
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

def extract_submission_info(submission):
    """Extract and return useful information about a submission"""
    # Format created timestamp
    created_date = datetime.fromtimestamp(submission.created_utc)
    
    info = {
        "id": submission.id,
        "title": submission.title,
        "author": submission.author.name if submission.author else "[deleted]",
        "score": submission.score,
        "upvote_ratio": submission.upvote_ratio,
        "comments": submission.num_comments,
        "created": created_date.strftime("%Y-%m-%d %H:%M:%S"),
        "created_utc": submission.created_utc,
        "permalink": f"https://reddit.com{submission.permalink}",
        "url": submission.url,
        "has_video": has_video(submission)
    }
    
    if info["has_video"]:
        info["video_url"] = get_video_url(submission)
    
    return info

def fetch_videos_from_subreddit(reddit, subreddit_name, limit=10, time_filter="day", min_score=10):
    """Fetch posts from a subreddit that contain videos"""
    logger.info(f"Fetching top {limit} posts from r/{subreddit_name} for time period: {time_filter}")
    
    subreddit = reddit.subreddit(subreddit_name)
    video_posts = []
    
    # Get top posts for the specified time period
    for submission in subreddit.top(time_filter=time_filter, limit=limit*2):  # Fetch more to filter
        # Skip posts with low scores
        if submission.score < min_score:
            continue
            
        # Check if the post has a video
        if has_video(submission):
            info = extract_submission_info(submission)
            video_posts.append(info)
            
            if len(video_posts) >= limit:
                break
    
    logger.info(f"Found {len(video_posts)} video posts")
    return video_posts

def process_videos(posts, download=True):
    """Process list of video posts"""
    downloaded = []
    
    for i, post in enumerate(posts):
        logger.info(f"[{i+1}/{len(posts)}] Processing: {post['title']}")
        
        if download and 'video_url' in post:
            output_file = f"{DOWNLOAD_FOLDER}/{post['id']}.mp4"
            
            # Check if already downloaded
            if os.path.exists(output_file):
                logger.info(f"Video already exists: {output_file}")
                file_size = os.path.getsize(output_file) / (1024 * 1024)  # Size in MB
                post['downloaded'] = {"path": output_file, "size_mb": file_size}
                downloaded.append(post)
                continue
                
            # Download the video
            result = download_video(post['video_url'], output_file)
            if result:
                post['downloaded'] = result
                downloaded.append(post)
    
    return downloaded

def main():
    """Main function"""
    # Initialize Reddit client
    reddit = initialize_reddit_client()
    
    # Create output directory if it doesn't exist
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
    # Fetch video posts
    posts = fetch_videos_from_subreddit(
        reddit, 
        SUBREDDIT, 
        limit=MAX_POSTS,
        time_filter=FETCH_PERIOD, 
        min_score=MIN_SCORE
    )
    
    if not posts:
        logger.warning(f"No video posts found in r/{SUBREDDIT}")
        return
    
    # Write post information to JSON file
    output_json = f"{DOWNLOAD_FOLDER}/combat_footage_posts.json"
    with open(output_json, 'w') as f:
        json.dump(posts, f, indent=2)
    logger.info(f"Saved post information to {output_json}")
    
    # Process and download videos
    downloaded = process_videos(posts)
    
    logger.info(f"Successfully downloaded {len(downloaded)} videos")
    
    # Print a summary of downloaded videos
    if downloaded:
        print("\nSummary of Downloaded Videos:")
        print("-" * 80)
        for i, post in enumerate(downloaded):
            print(f"{i+1}. {post['title']}")
            print(f"   Score: {post['score']} | Comments: {post['comments']} | Posted: {post['created']}")
            print(f"   File: {post['downloaded']['path']} ({post['downloaded']['size_mb']:.2f} MB)")
            print(f"   URL: {post['permalink']}")
            print("-" * 80)

if __name__ == "__main__":
    main()
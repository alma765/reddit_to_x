import os

# Reddit API credentials
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'python:reddit-to-twitter-bot:v1.0 (by /u/yourUsername)')
REDDIT_USERNAME = os.getenv('REDDIT_USERNAME', '')
REDDIT_PASSWORD = os.getenv('REDDIT_PASSWORD', '')

# Twitter API credentials (v2)
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY', '')
TWITTER_API_KEY_SECRET = os.getenv('TWITTER_API_KEY_SECRET', '')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN', '')
TWITTER_ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET', '')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN', '')

# Bot configuration
SUBREDDITS = os.getenv('SUBREDDITS', 'videos,gifs,funny').split(',')
DOWNLOAD_FOLDER = os.getenv('DOWNLOAD_FOLDER', './downloads')
MAX_VIDEO_SIZE_MB = int(os.getenv('MAX_VIDEO_SIZE_MB', '15'))  # Twitter has a 15MB limit for videos
MAX_VIDEO_DURATION_SECONDS = int(os.getenv('MAX_VIDEO_DURATION_SECONDS', '140'))  # Twitter has a 140s limit
MIN_VIDEO_DURATION_SECONDS = int(os.getenv('MIN_VIDEO_DURATION_SECONDS', '3'))
POSTS_LIMIT = int(os.getenv('POSTS_LIMIT', '25'))  # Number of Reddit posts to fetch per subreddit
POST_INTERVAL_MINUTES = int(os.getenv('POST_INTERVAL_MINUTES', '60'))  # How often to post to Twitter

# Database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///redditbot.db')

# Flask configuration
SESSION_SECRET = os.getenv('SESSION_SECRET', 'dev_session_secret_key')

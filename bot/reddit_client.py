import logging
import praw
import requests
import os
import re
import html
import subprocess
import shutil
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
    
    def fetch_content(self, subreddits=None, limit=None, content_type="video"):
        """
        Fetch posts from specified subreddits based on content type
        
        Args:
            subreddits (list): List of subreddit names to fetch from
            limit (int): Number of posts to fetch per subreddit
            content_type (str): Type of content to fetch ("video", "image", or "all")
            
        Returns:
            list: List of submission objects containing requested content
        """
        if subreddits is None:
            subreddits = SUBREDDITS
        
        if limit is None:
            limit = POSTS_LIMIT
            
        logger.info(f"Fetching {content_type} posts from {', '.join(subreddits)}")
        
        content_posts = []
        
        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                
                # Fetch hot posts from the subreddit
                submission_count = 0
                for submission in subreddit.hot(limit=limit):
                    submission_count += 1
                    logger.info(f"Checking submission: {submission.id} - {submission.title}")
                    
                    has_video = self._has_video(submission)
                    has_image = self._has_image(submission)
                    
                    if content_type == "video" and has_video:
                        logger.info(f"Found video: {submission.title} in r/{subreddit_name}")
                        content_posts.append(submission)
                    elif content_type == "image" and has_image:
                        logger.info(f"Found image: {submission.title} in r/{subreddit_name}")
                        content_posts.append(submission)
                    elif content_type == "all" and (has_video or has_image):
                        logger.info(f"Found content: {submission.title} in r/{subreddit_name}")
                        content_posts.append(submission)
                    else:
                        logger.info(f"No matching content found in submission: {submission.id}")
                
                logger.info(f"Checked {submission_count} submissions, found {len(content_posts)} matching posts")
                
            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit_name}: {str(e)}")
        
        logger.info(f"Found {len(content_posts)} {content_type} posts across all subreddits")
        return content_posts
        
    def fetch_videos(self, subreddits=None, limit=None):
        """
        Fetch video posts from specified subreddits (legacy method)
        
        Args:
            subreddits (list): List of subreddit names to fetch from
            limit (int): Number of posts to fetch per subreddit
            
        Returns:
            list: List of submission objects containing videos
        """
        return self.fetch_content(subreddits, limit, content_type="video")

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
        
    def _has_image(self, submission):
        """
        Check if a submission has an image attached
        
        Args:
            submission: Reddit submission object
            
        Returns:
            bool: True if submission has an image, False otherwise
        """
        # Return False if it has a video (we prefer to handle it as a video)
        if self._has_video(submission):
            return False
            
        # Get URL for checking
        url = submission.url.lower()
        
        # Check common image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        if any(url.endswith(ext) for ext in image_extensions):
            return True
            
        # Check Reddit's gallery posts
        if hasattr(submission, 'is_gallery') and submission.is_gallery:
            return True
            
        # Check for Imgur image links
        if 'imgur.com' in url and '/a/' not in url:
            # If it's not already identified as a video (checked above)
            # and it's an imgur link, it's likely an image
            return True
            
        # Check for Reddit image previews
        if hasattr(submission, 'preview') and submission.preview:
            try:
                if 'images' in submission.preview and len(submission.preview['images']) > 0:
                    return True
            except:
                pass
                
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
                # Just return the submission ID for Reddit videos
                # We'll handle the special download process in the download_video method
                return f"reddit:{submission.id}"
        
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
            
            # Special handling for Reddit videos (which have separate audio and video streams)
            if video_url.startswith('reddit:'):
                # Extract submission ID from the URL
                submission_id = video_url.split(':')[1]
                return self._download_reddit_video(submission_id, download_path)
            
            # Standard download for all other videos
            # First, try using FFmpeg for better quality and audio handling
            try:
                logger.info(f"Attempting to download with FFmpeg from {video_url}")
                
                # Advanced FFmpeg command with audio handling
                command = [
                    'ffmpeg',
                    '-i', video_url,
                    '-c:v', 'copy',       # Copy video without re-encoding
                    '-c:a', 'aac',        # Convert audio to AAC for compatibility
                    '-b:a', '128k',       # Good audio quality
                    '-af', 'volume=1.5',  # Boost volume slightly
                    '-y',                 # Overwrite output if it exists
                    download_path
                ]
                
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    # FFmpeg successful, check size of the file
                    final_size_mb = os.path.getsize(download_path) / (1024 * 1024)
                    
                    # If we've downloaded more than 100MB, abort
                    if final_size_mb > 100:
                        logger.warning(f"Downloaded file exceeds 100MB - too large for Twitter: {final_size_mb:.2f}MB")
                        os.remove(download_path)
                        return None
                    
                    logger.info(f"Successfully downloaded video with FFmpeg to {download_path} (Size: {final_size_mb:.2f}MB)")
                    
                    # Check if there's audio in the output
                    stderr_output = stderr.decode('utf-8')
                    if "Audio:" in stderr_output:
                        logger.info("Audio stream detected in the downloaded file")
                    else:
                        logger.info("No audio stream detected in the downloaded file")
                    
                    return download_path
                else:
                    logger.warning(f"FFmpeg download failed: {stderr.decode('utf-8')}")
                    # Fall back to regular download method
            except Exception as e:
                logger.warning(f"FFmpeg download attempt failed: {str(e)}")
                # Fall back to regular download method
            
            # Fallback to standard download with requests
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
            
            # Download the video using requests as fallback
            logger.info("Falling back to requests for download")
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
            
    def _download_reddit_video(self, submission_id, download_path):
        """
        Download a Reddit video with audio
        
        Args:
            submission_id (str): Reddit submission ID
            download_path (str): Path where the video should be saved
            
        Returns:
            str: Path to the downloaded video or None if download failed
        """
        try:
            # Get the submission object
            submission = self.reddit.submission(id=submission_id)
            
            if not hasattr(submission, 'media') or not submission.media or 'reddit_video' not in submission.media:
                logger.error(f"No reddit_video found in submission {submission_id}")
                return None
            
            # Get the video URL
            video_url = submission.media['reddit_video']['fallback_url']
            
            # Create temporary paths for video and audio files
            temp_video_path = download_path + ".temp_video.mp4"
            temp_audio_path = download_path + ".temp_audio.mp4"
            
            # Check if we have an HLS URL for the video
            # Default to using regular download as fallback
            use_regular_download = False
            
            hls_url = None
            if hasattr(submission, 'media') and submission.media and 'reddit_video' in submission.media:
                if 'hls_url' in submission.media['reddit_video']:
                    hls_url = submission.media['reddit_video']['hls_url']
                    logger.info(f"Found HLS URL: {hls_url}")
            
            if hls_url:
                # Use FFmpeg to download directly from the HLS source (preserves audio automatically)
                logger.info(f"Using FFmpeg to download and process video from HLS URL")
                
                # More advanced FFmpeg command to prioritize audio streams
                command = [
                    'ffmpeg',
                    '-i', hls_url,
                    '-c:v', 'copy',      # Copy video stream without re-encoding
                    '-c:a', 'aac',       # Convert audio to AAC for better compatibility
                    '-b:a', '128k',      # Set audio bitrate to reasonable quality
                    '-af', 'volume=1.5', # Boost audio volume slightly for better audibility
                    '-shortest',         # Use shortest stream duration
                    '-y',                # Overwrite output file if it exists
                    download_path
                ]
                
                try:
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        logger.error(f"Error downloading with FFmpeg: {stderr.decode('utf-8')}")
                        # Fall back to regular download method
                        logger.warning("Falling back to regular download without audio")
                        use_regular_download = True
                    else:
                        logger.info(f"Successfully downloaded video with FFmpeg to {download_path}")
                        
                        # Check the output to see if it mentions audio streams
                        stderr_text = stderr.decode('utf-8')
                        if "Audio:" in stderr_text:
                            logger.info("Audio stream found and included in the download")
                        else:
                            logger.info("No audio stream detected in the downloaded file")
                        
                        # Successfully downloaded with possible audio
                        return download_path
                except Exception as e:
                    logger.error(f"Exception running FFmpeg: {str(e)}")
                    use_regular_download = True
            else:
                use_regular_download = True
            
            # Regular download method as fallback
            if use_regular_download:
                # Download video
                logger.info(f"Downloading video stream from {video_url}")
                video_response = requests.get(video_url, stream=True)
                video_response.raise_for_status()
                
                with open(download_path, 'wb') as f:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Downloaded video without audio to {download_path}")
                # Return the video-only version as we couldn't get the audio
                return download_path
            
            # Clean up temporary files
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            
            # Check the final size
            final_size_mb = os.path.getsize(download_path) / (1024 * 1024)
            logger.info(f"Downloaded Reddit video with ID {submission_id} to {download_path} (Size: {final_size_mb:.2f} MB)")
            
            return download_path
            
        except Exception as e:
            logger.error(f"Error downloading Reddit video {submission_id}: {str(e)}")
            # Clean up any temp files
            for path in [download_path, download_path + ".temp_video.mp4", download_path + ".temp_audio.mp4"]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            return None
    
    def get_image_url(self, submission):
        """
        Extract the direct image URL from a Reddit submission
        
        Args:
            submission: Reddit submission object
            
        Returns:
            str: Direct URL to the image or None if not found
        """
        # If it's already a direct image URL, return it
        url = submission.url.lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        if any(url.endswith(ext) for ext in image_extensions):
            return submission.url
            
        # Check for Reddit gallery
        if hasattr(submission, 'is_gallery') and submission.is_gallery:
            # Get the first image from the gallery
            try:
                if hasattr(submission, 'media_metadata') and submission.media_metadata:
                    for media_id in submission.media_metadata:
                        item = submission.media_metadata[media_id]
                        if item['e'] == 'Image':  # 'e' stands for 'extension'
                            if 's' in item and 'u' in item['s']:  # 's' is source, 'u' is URL
                                return item['s']['u']
            except Exception as e:
                logger.error(f"Error extracting gallery image: {str(e)}")
                
        # Check for Reddit image previews
        if hasattr(submission, 'preview') and submission.preview:
            try:
                if 'images' in submission.preview and len(submission.preview['images']) > 0:
                    for resolution in ['source', 'resolutions']:
                        if resolution in submission.preview['images'][0]:
                            if 'url' in submission.preview['images'][0][resolution]:
                                return submission.preview['images'][0][resolution]['url']
            except Exception as e:
                logger.error(f"Error extracting preview image: {str(e)}")
                
        # Special handling for Imgur links that aren't direct image links
        if 'imgur.com' in url and not any(url.endswith(ext) for ext in image_extensions):
            # Try to convert to direct image link
            if '/a/' not in url and '/gallery/' not in url:  # Not an album
                # Strip query parameters
                url = url.split('?')[0]
                # Remove trailing slash if present
                if url.endswith('/'):
                    url = url[:-1]
                # Add file extension
                if not any(ext in url for ext in image_extensions):
                    url += '.jpg'  # Default to jpg
                return url
                
        # Fallback: return the original URL and hope for the best
        return submission.url
        
    def download_image(self, image_url, download_path):
        """
        Download an image from a URL to the specified path
        
        Args:
            image_url (str): URL of the image to download
            download_path (str): Path where the image should be saved
            
        Returns:
            str: Path to the downloaded image or None if download failed
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            
            # Download the image
            logger.info(f"Downloading image from {image_url} to {download_path}")
            
            # Unquote the URL to handle HTML-encoded characters
            image_url = html.unescape(image_url)
            
            response = requests.get(image_url, stream=True, headers={'User-Agent': REDDIT_USER_AGENT})
            response.raise_for_status()
            
            # Save the image
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # Verify the image was downloaded correctly
            if os.path.getsize(download_path) == 0:
                logger.error(f"Downloaded image is empty: {download_path}")
                os.remove(download_path)
                return None
                
            logger.info(f"Successfully downloaded image to {download_path}")
            return download_path
            
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {str(e)}")
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
        # Determine content type
        is_gallery = hasattr(submission, 'is_gallery') and submission.is_gallery
        is_video = self._has_video(submission)
        is_image = self._has_image(submission)
        
        if is_gallery:
            content_type = 'gallery'
        elif is_video:
            content_type = 'video'
        elif is_image:
            content_type = 'image'
        else:
            content_type = 'text'
        
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
            'content_type': content_type,
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
            
        # Add content type indicator
        if metadata['content_type'] == 'video':
            tweet += " [Video]"
        elif metadata['content_type'] == 'image':
            tweet += " [Photo]"
        elif metadata['content_type'] == 'gallery':
            tweet += " [Gallery]"
        
        return tweet

    def get_gallery_image_urls(self, submission):
        """
        Extract all image URLs from a Reddit gallery post
        
        Args:
            submission: Reddit submission object
            
        Returns:
            list: List of direct URLs to all images in the gallery, or empty list if not a gallery
                 or if extraction fails
        """
        image_urls = []
        
        # Check if this is a gallery post
        if not (hasattr(submission, 'is_gallery') and submission.is_gallery):
            return image_urls
            
        try:
            # If it's a Reddit gallery, extract all images
            if hasattr(submission, 'media_metadata') and submission.media_metadata:
                # First get all media IDs in order if gallery_data is available
                ordered_ids = []
                if hasattr(submission, 'gallery_data') and submission.gallery_data:
                    for item in submission.gallery_data['items']:
                        ordered_ids.append(item['media_id'])
                
                # If we couldn't get ordered IDs, just use the keys from media_metadata
                if not ordered_ids:
                    ordered_ids = list(submission.media_metadata.keys())
                
                # Process all media IDs
                for media_id in ordered_ids:
                    if media_id in submission.media_metadata:
                        item = submission.media_metadata[media_id]
                        if item['e'] == 'Image':  # 'e' stands for 'extension'
                            if 's' in item and 'u' in item['s']:  # 's' is source, 'u' is URL
                                image_urls.append(item['s']['u'])
                                
                logger.info(f"Found {len(image_urls)} images in Reddit gallery")
        except Exception as e:
            logger.error(f"Error extracting gallery images: {str(e)}")
            
        return image_urls
        
    def download_gallery_images(self, submission, base_path):
        """
        Download all images from a Reddit gallery post
        
        Args:
            submission: Reddit submission object
            base_path: Base path for downloading images, without extension
            
        Returns:
            list: List of paths to downloaded images, or empty list if download failed
        """
        image_paths = []
        
        # Get all image URLs from the gallery
        image_urls = self.get_gallery_image_urls(submission)
        if not image_urls:
            logger.warning(f"No images found in gallery post: {submission.id}")
            return image_paths
            
        # Download each image with a unique filename
        for i, image_url in enumerate(image_urls):
            # Create a unique path for each image
            if i == 0:
                # First image uses base path directly
                image_path = f"{base_path}.jpg"
            else:
                # Additional images append index
                image_path = f"{base_path}_{i+1}.jpg"
                
            # Download the image
            downloaded_path = self.download_image(image_url, image_path)
            if downloaded_path:
                image_paths.append(downloaded_path)
                
        logger.info(f"Downloaded {len(image_paths)} out of {len(image_urls)} gallery images")
        return image_paths

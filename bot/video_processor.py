import logging
import os
import cv2
import shutil
from datetime import datetime

from config import (
    DOWNLOAD_FOLDER,
    MAX_VIDEO_SIZE_MB,
    MAX_VIDEO_DURATION_SECONDS,
    MIN_VIDEO_DURATION_SECONDS
)

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, download_folder=None):
        """
        Initialize the video processor
        
        Args:
            download_folder (str): Folder to store downloaded videos
        """
        self.download_folder = download_folder or DOWNLOAD_FOLDER
        
        # Ensure download folder exists
        os.makedirs(self.download_folder, exist_ok=True)
        logger.info(f"Video processor initialized with download folder: {self.download_folder}")
    
    def validate_video(self, video_path):
        """
        Validate a video file for integrity and compatibility
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            dict: Validation results with keys 'valid', 'duration', 'size_bytes', 'error'
        """
        result = {
            'valid': False,
            'duration': 0,
            'size_bytes': 0,
            'error': None
        }
        
        if not os.path.exists(video_path):
            result['error'] = f"Video file not found: {video_path}"
            logger.error(result['error'])
            return result
        
        try:
            # Get file size
            file_size = os.path.getsize(video_path)
            result['size_bytes'] = file_size
            
            # Check if file size exceeds Twitter's limit
            max_size_bytes = MAX_VIDEO_SIZE_MB * 1024 * 1024
            if file_size > max_size_bytes:
                result['error'] = f"Video size ({file_size/1024/1024:.2f}MB) exceeds Twitter limit of {MAX_VIDEO_SIZE_MB}MB"
                logger.warning(result['error'])
                return result
            
            # Open the video to check integrity and get duration
            video = cv2.VideoCapture(video_path)
            
            if not video.isOpened():
                result['error'] = "Could not open video file, it may be corrupted or in an unsupported format"
                logger.error(result['error'])
                return result
            
            # Get video properties
            fps = video.get(cv2.CAP_PROP_FPS)
            frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Calculate duration
            if fps > 0 and frame_count > 0:
                duration = frame_count / fps
                result['duration'] = duration
                
                # Check video duration against limits
                if duration > MAX_VIDEO_DURATION_SECONDS:
                    result['error'] = f"Video duration ({duration:.2f}s) exceeds Twitter limit of {MAX_VIDEO_DURATION_SECONDS}s"
                    logger.warning(result['error'])
                    return result
                
                if duration < MIN_VIDEO_DURATION_SECONDS:
                    result['error'] = f"Video duration ({duration:.2f}s) is too short (min: {MIN_VIDEO_DURATION_SECONDS}s)"
                    logger.warning(result['error'])
                    return result
            else:
                result['error'] = "Could not determine video duration (FPS or frame count is zero)"
                logger.warning(result['error'])
                return result
            
            # Make sure we can read at least one frame
            ret, frame = video.read()
            if not ret:
                result['error'] = "Could not read video frame, the file may be corrupted"
                logger.error(result['error'])
                return result
            
            # Successfully validated
            result['valid'] = True
            logger.info(f"Video validated successfully: {video_path} ({result['duration']:.2f}s, {result['size_bytes']/1024/1024:.2f}MB)")
            
            return result
            
        except Exception as e:
            result['error'] = f"Error validating video: {str(e)}"
            logger.error(result['error'], exc_info=True)
            return result
        finally:
            if 'video' in locals():
                video.release()
    
    def generate_filename(self, reddit_id):
        """
        Generate a unique filename for a Reddit post
        
        Args:
            reddit_id (str): Reddit post ID
            
        Returns:
            str: Full path to the file
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{reddit_id}_{timestamp}.mp4"
        return os.path.join(self.download_folder, filename)
    
    def cleanup_old_videos(self, max_age_days=7):
        """
        Remove videos older than the specified age
        
        Args:
            max_age_days (int): Maximum age of videos in days
        """
        try:
            current_time = datetime.now()
            count = 0
            
            for filename in os.listdir(self.download_folder):
                if filename.endswith(('.mp4', '.mov', '.avi', '.webm')):
                    file_path = os.path.join(self.download_folder, filename)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # Calculate file age in days
                    age_days = (current_time - file_modified).days
                    
                    if age_days > max_age_days:
                        os.remove(file_path)
                        count += 1
                        logger.debug(f"Removed old video: {file_path} (age: {age_days} days)")
            
            if count > 0:
                logger.info(f"Cleaned up {count} old videos")
                
        except Exception as e:
            logger.error(f"Error during video cleanup: {str(e)}")

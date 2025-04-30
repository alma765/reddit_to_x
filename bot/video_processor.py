import logging
import os
import cv2
import shutil
import subprocess
import tempfile
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
    
    def calculate_video_hash(self, video_path, frames_to_sample=5):
        """
        Calculate a simple hash based on video resolution and sampled frames
        
        Args:
            video_path (str): Path to the video file
            frames_to_sample (int): Number of frames to sample for the hash
            
        Returns:
            str: A hash string representing the video, or None if calculation fails
        """
        try:
            video = cv2.VideoCapture(video_path)
            if not video.isOpened():
                logger.error(f"Could not open video for hashing: {video_path}")
                return None
                
            # Get video properties
            width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = video.get(cv2.CAP_PROP_FPS)
            frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if frame_count <= 0 or fps <= 0:
                logger.error(f"Invalid frame count or FPS for video: {video_path}")
                return None
                
            # Calculate frames to sample at evenly distributed positions
            frame_positions = []
            if frame_count > frames_to_sample:
                step = frame_count // (frames_to_sample + 1)
                frame_positions = [step * (i + 1) for i in range(frames_to_sample)]
            else:
                # If video has fewer frames than samples, use all frames
                frame_positions = list(range(frame_count))
            
            # Sample frames and calculate simple hash
            frame_hashes = []
            for pos in frame_positions:
                video.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ret, frame = video.read()
                if not ret:
                    continue
                    
                # Resize frame to a small size for faster processing
                small_frame = cv2.resize(frame, (32, 32))
                # Convert to grayscale
                gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                # Calculate average pixel value
                avg_value = gray_frame.mean()
                frame_hashes.append(str(int(avg_value)))
            
            video.release()
            
            # Create a hash string
            video_hash = f"{width}x{height}_{fps:.2f}_{''.join(frame_hashes)}"
            return video_hash
            
        except Exception as e:
            logger.error(f"Error calculating video hash: {str(e)}")
            return None
    
    def is_duplicate_content(self, video_path):
        """
        Check if a video has similar content to any previously processed video
        
        Args:
            video_path (str): Path to the video file
            
        Returns:
            bool: True if similar content was found, False otherwise
        """
        try:
            from models import Post
            from app import db
            
            # Calculate hash for current video
            video_hash = self.calculate_video_hash(video_path)
            if not video_hash:
                return False
                
            # Basic hash structure: "{width}x{height}_{fps:.2f}_{pixel_means}"
            # Extract dimensions and FPS to do a relaxed match
            dimensions, fps, _ = video_hash.split('_', 2)
            
            # Check for any videos with similar dimensions and FPS
            # This is just a first filter to avoid unnecessary hash comparisons
            # ONLY check against videos that were successfully posted to Twitter
            recent_posts = db.session.query(Post).filter(
                Post.video_path != None,
                Post.posted_to_twitter == True  # Only consider successfully posted videos as duplicates
            ).order_by(Post.id.desc()).limit(20).all()
            
            # Check each recent video
            for post in recent_posts:
                if not post.video_path or not os.path.exists(post.video_path):
                    continue
                    
                # Get hash for this video
                existing_hash = self.calculate_video_hash(post.video_path)
                if not existing_hash:
                    continue
                    
                # If exact hash match, definitely a duplicate
                if existing_hash == video_hash:
                    logger.warning(f"Found exact hash match between new video and {post.reddit_id}")
                    return True
                    
                # Check for similar content with some tolerance
                existing_dimensions, existing_fps, existing_pixel_data = existing_hash.split('_', 2)
                
                # Same dimensions is a strong indicator
                if dimensions == existing_dimensions:
                    # Compare pixel data with some tolerance
                    matching_pixels = 0
                    for i, digit in enumerate(existing_pixel_data):
                        if i < len(existing_pixel_data) and digit == existing_pixel_data[i]:
                            matching_pixels += 1
                    
                    # If more than 70% of the sampled pixel means match, consider it a duplicate
                    similarity = matching_pixels / min(len(existing_pixel_data), len(existing_pixel_data))
                    if similarity > 0.7:
                        logger.warning(f"Found similar content match ({similarity:.2f}) with {post.reddit_id}")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking for duplicate content: {str(e)}")
            return False
            
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
                # Still valid for compression purposes, we'll just report the size issue
                result['error'] = f"Video size ({file_size/1024/1024:.2f}MB) exceeds Twitter limit of {MAX_VIDEO_SIZE_MB}MB"
                logger.warning(result['error'])
                # Instead of returning early, set valid to true but keep the error message
                # This allows the compression method to attempt to compress oversized files
                result['valid'] = True
            
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
    
    def generate_filename(self, reddit_id, extension=".mp4"):
        """
        Generate a unique filename for a Reddit post
        
        Args:
            reddit_id (str): Reddit post ID
            extension (str): File extension to use (.mp4, .jpg, etc.)
            
        Returns:
            str: Full path to the file
        """
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{reddit_id}_{timestamp}{extension}"
        return os.path.join(self.download_folder, filename)
    
    def cleanup_old_videos(self, max_age_days=7):
        """
        Remove media files (videos and images) older than the specified age
        
        Args:
            max_age_days (int): Maximum age of files in days
        """
        try:
            current_time = datetime.now()
            video_count = 0
            image_count = 0
            
            for filename in os.listdir(self.download_folder):
                # Check video files
                if filename.endswith(('.mp4', '.mov', '.avi', '.webm')):
                    file_path = os.path.join(self.download_folder, filename)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # Calculate file age in days
                    age_days = (current_time - file_modified).days
                    
                    if age_days > max_age_days:
                        os.remove(file_path)
                        video_count += 1
                        logger.debug(f"Removed old video: {file_path} (age: {age_days} days)")
                
                # Check image files
                elif filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    file_path = os.path.join(self.download_folder, filename)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    # Calculate file age in days
                    age_days = (current_time - file_modified).days
                    
                    if age_days > max_age_days:
                        os.remove(file_path)
                        image_count += 1
                        logger.debug(f"Removed old image: {file_path} (age: {age_days} days)")
            
            total_count = video_count + image_count
            if total_count > 0:
                logger.info(f"Cleaned up {video_count} old videos and {image_count} old images")
                
        except Exception as e:
            logger.error(f"Error during media cleanup: {str(e)}")
            
    def compress_video(self, input_path, target_size_mb=None, max_width=1280):
        """
        Compress a video to meet Twitter's size and duration requirements
        
        Args:
            input_path (str): Path to the input video
            target_size_mb (float): Target size in MB, defaults to MAX_VIDEO_SIZE_MB - 1
            max_width (int): Maximum width for the video (height will be adjusted to maintain aspect ratio)
            
        Returns:
            str: Path to the compressed video if successful, None otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input video not found: {input_path}")
            return None
            
        # Default target size is 1MB less than Twitter's limit for safety
        if target_size_mb is None:
            target_size_mb = MAX_VIDEO_SIZE_MB - 1
            
        try:
            # Get original file size and validate video
            original_size_mb = os.path.getsize(input_path) / (1024 * 1024)
            validation = self.validate_video(input_path)
            
            if not validation['valid']:
                logger.error(f"Cannot compress invalid video: {validation['error']}")
                return None
                
            duration = validation.get('duration', 0)
            
            # Adjust compression parameters based on video size
            # For extremely large videos, use more aggressive compression
            if original_size_mb > 50:
                logger.warning(f"Video is very large ({original_size_mb:.2f}MB), using aggressive compression")
                target_size_mb = MAX_VIDEO_SIZE_MB - 2  # Even more margin for safety
                max_width = min(max_width, 854)  # Lower resolution (480p equivalent)
            # For large videos, use stronger compression
            elif original_size_mb > 20:
                logger.warning(f"Video is large ({original_size_mb:.2f}MB), using stronger compression")
                target_size_mb = MAX_VIDEO_SIZE_MB - 1.5  # More margin
                max_width = min(max_width, 1024)  # 720p equivalent
                
            # Determine if we need to handle duration issues
            needs_duration_fix = False
            speed_filter = ""
            audio_filter = ""
            
            # If duration exceeds Twitter's limit by a small amount, speed up the video
            if duration > MAX_VIDEO_DURATION_SECONDS and duration <= MAX_VIDEO_DURATION_SECONDS * 1.1:
                # Calculate required speedup factor (add a little buffer to be safe)
                speed_factor = duration / (MAX_VIDEO_DURATION_SECONDS * 0.98)
                logger.info(f"Video duration ({duration:.2f}s) slightly exceeds Twitter limit of {MAX_VIDEO_DURATION_SECONDS}s")
                logger.info(f"Speeding up video by factor of {speed_factor:.2f}x to fit within limit")
                
                # For video speedup, we use setpts filter
                speed_filter = f",setpts={1/speed_factor}*PTS"
                
                # For audio speedup (atempo only supports 0.5-2.0 range)
                if speed_factor <= 2.0:
                    audio_filter = f"atempo={speed_factor}"
                else:
                    # Chain multiple atempo filters for higher speeds
                    audio_filter = "atempo=2.0,atempo=" + str(speed_factor/2.0)
                
                # Adjust effective duration for bitrate calculations
                duration = duration / speed_factor
                needs_duration_fix = True
                
            # If duration exceeds Twitter's limit by a large amount, trim it
            elif duration > MAX_VIDEO_DURATION_SECONDS * 1.1:
                logger.info(f"Video duration ({duration:.2f}s) significantly exceeds Twitter limit of {MAX_VIDEO_DURATION_SECONDS}s")
                logger.info(f"Trimming video to first {MAX_VIDEO_DURATION_SECONDS} seconds")
                
                # For trimming, we use the trim filter
                speed_filter = f",trim=0:{MAX_VIDEO_DURATION_SECONDS},setpts=PTS-STARTPTS"
                audio_filter = f"atrim=0:{MAX_VIDEO_DURATION_SECONDS},asetpts=PTS-STARTPTS"
                
                # Adjust effective duration for bitrate calculations
                duration = MAX_VIDEO_DURATION_SECONDS
                needs_duration_fix = True
            
            # If already under target size and no duration issues, return original
            if original_size_mb <= target_size_mb and not needs_duration_fix:
                logger.info(f"Video already meets all requirements: {original_size_mb:.2f}MB, {duration:.2f}s")
                return input_path
                
            logger.info(f"Processing video: {input_path} (Size: {original_size_mb:.2f}MB, Duration: {duration:.2f}s)")
            
            # Get video info using OpenCV
            video = cv2.VideoCapture(input_path)
            width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = video.get(cv2.CAP_PROP_FPS)
            video.release()
            
            # Calculate new dimensions while maintaining aspect ratio
            if width > max_width:
                new_width = max_width
                new_height = int(height * (max_width / width))
            else:
                new_width = width
                new_height = height
            
            # Ensure dimensions are even (required by some codecs)
            new_width = new_width - (new_width % 2)
            new_height = new_height - (new_height % 2)
                
            # Create output filename
            input_dir, input_filename = os.path.split(input_path)
            base_name, ext = os.path.splitext(input_filename)
            output_path = os.path.join(input_dir, f"{base_name}_compressed{ext}")
            
            # Calculate target bitrate based on target size and duration
            # Bitrate = (target_size_bytes * 8) / duration_seconds
            try:
                # Calculate target bitrate (in kbps)
                target_size_kb = target_size_mb * 1024
                target_bitrate = int((target_size_kb * 8) / duration)
                # Minimum reasonable bitrate
                target_bitrate = max(target_bitrate, 200)
                logger.info(f"Target bitrate: {target_bitrate}kbps for {duration:.2f}s video")
                
                # Skip OpenCV compression since it strips audio
                # Go directly to FFmpeg for compression to preserve audio
                try:
                    fd, temp_output = tempfile.mkstemp(suffix='.mp4')
                    os.close(fd)
                    
                    # Build the video filter string
                    video_filter = f"scale={new_width}:{new_height}{speed_filter}"
                    
                    # FFmpeg command for compression with better audio handling
                    command = [
                        'ffmpeg',
                        '-i', input_path,
                        '-c:v', 'libx264',
                        '-preset', 'medium',  # Balance between compression speed and quality
                        '-profile:v', 'main', # Good compatibility with Twitter
                        '-level', '4.0',      # Compatibility level
                        '-b:v', f'{target_bitrate}k',
                        '-maxrate', f'{target_bitrate * 1.5}k',
                        '-bufsize', f'{target_bitrate * 3}k',
                        '-vf', video_filter,
                    ]
                    
                    # Add audio filter if needed
                    if audio_filter:
                        command.extend(['-af', audio_filter])
                    
                    # Improved audio handling - prioritize audio quality
                    command.extend([
                        '-c:a', 'aac',
                        '-b:a', '128k',       # Default audio bitrate
                        '-ar', '48000',       # Standard audio sampling rate
                        '-ac', '2',           # Stereo audio
                        '-movflags', '+faststart',  # Optimize for web streaming
                        '-y',                 # Overwrite output file if it exists
                        temp_output
                    ])
                    
                    logger.info(f"Running FFmpeg command: {' '.join(command)}")
                    
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        logger.error(f"FFmpeg error: {stderr.decode('utf-8')}")
                        if os.path.exists(temp_output):
                            os.remove(temp_output)
                        return None
                    
                    # Check if the output file exists and meets the size requirement
                    if os.path.exists(temp_output):
                        final_size_mb = os.path.getsize(temp_output) / (1024 * 1024)
                        
                        # Verify duration meets requirements
                        output_validation = self.validate_video(temp_output)
                        if output_validation['valid']:
                            final_duration = output_validation['duration']
                            logger.info(f"Processed video stats: Size={final_size_mb:.2f}MB, Duration={final_duration:.2f}s")
                            
                            if final_duration > MAX_VIDEO_DURATION_SECONDS:
                                logger.error(f"Processed video still exceeds duration limit: {final_duration:.2f}s > {MAX_VIDEO_DURATION_SECONDS}s")
                                os.remove(temp_output)
                                return None
                        else:
                            logger.error(f"Processed video is invalid: {output_validation['error']}")
                            os.remove(temp_output)
                            return None
                        
                        if final_size_mb <= target_size_mb:
                            # Move temp file to output path
                            shutil.move(temp_output, output_path)
                            logger.info(f"Successfully processed video: {output_path}")
                            return output_path
                        else:
                            # Try one more time with lower bitrate
                            os.remove(temp_output)
                            lower_bitrate = int(target_bitrate * (target_size_mb / final_size_mb) * 0.9)
                            logger.info(f"Trying again with lower bitrate: {lower_bitrate}kbps")
                            
                            # Update bitrate in the command
                            for i, arg in enumerate(command):
                                if arg == '-b:v':
                                    command[i+1] = f'{lower_bitrate}k'
                                elif arg == '-maxrate':
                                    command[i+1] = f'{lower_bitrate * 1.5}k'
                                elif arg == '-bufsize':
                                    command[i+1] = f'{lower_bitrate * 3}k'
                            
                            fd, temp_output = tempfile.mkstemp(suffix='.mp4')
                            os.close(fd)
                            command[-1] = temp_output
                            
                            logger.info(f"Running FFmpeg command (attempt 2): {' '.join(command)}")
                            
                            process = subprocess.Popen(
                                command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            stdout, stderr = process.communicate()
                            
                            if process.returncode != 0:
                                logger.error(f"FFmpeg error in second attempt: {stderr.decode('utf-8')}")
                                if os.path.exists(temp_output):
                                    os.remove(temp_output)
                                return None
                                
                            if os.path.exists(temp_output):
                                final_size_mb = os.path.getsize(temp_output) / (1024 * 1024)
                                
                                # Verify duration meets requirements
                                output_validation = self.validate_video(temp_output)
                                if output_validation['valid'] and output_validation['duration'] <= MAX_VIDEO_DURATION_SECONDS:
                                    logger.info(f"Final processed video: Size={final_size_mb:.2f}MB, Duration={output_validation['duration']:.2f}s")
                                    shutil.move(temp_output, output_path)
                                    return output_path
                                else:
                                    logger.error(f"Final processed video is invalid or too long")
                                    os.remove(temp_output)
                                    return None
                    
                    return None
                    
                except Exception as e:
                    logger.error(f"Error using FFmpeg for compression: {e}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error calculating bitrate: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error compressing video: {e}")
            return None

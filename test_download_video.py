import os
import sys
import logging
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import our modules
from bot.video_processor import VideoProcessor

def download_and_validate_video(video_url, video_id):
    """Download and validate a video from a URL"""
    try:
        logger.info(f"Processing video: {video_id}")
        logger.info(f"URL: {video_url}")
        
        # Create video processor
        video_processor = VideoProcessor()
        
        # Generate a filename for the video
        download_path = f"./downloads/{video_id}.mp4"
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        
        # First, check the total file size
        response = requests.head(video_url, allow_redirects=True)
        size_mb = None
        if 'Content-Length' in response.headers:
            size_bytes = int(response.headers['Content-Length'])
            size_mb = size_bytes / (1024 * 1024)
            logger.info(f"Video size: {size_mb:.2f} MB")
            
        # Download the video
        logger.info(f"Downloading to: {download_path}")
        download_response = requests.get(video_url, stream=True)
        download_response.raise_for_status()
        
        # Save the video to the specified path
        with open(download_path, 'wb') as f:
            for chunk in download_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Check the final size
        final_size_mb = os.path.getsize(download_path) / (1024 * 1024)
        logger.info(f"Downloaded video (Size: {final_size_mb:.2f} MB)")
        
        # Validate the video
        validation = video_processor.validate_video(download_path)
        
        if validation['valid']:
            logger.info(f"Video validation successful")
            logger.info(f"Duration: {validation['duration']:.2f}s, Size: {validation['size_bytes']/1024/1024:.2f}MB")
        else:
            logger.warning(f"Video validation failed: {validation['error']}")
            
            # If it's a size issue, try compression
            if validation['error'] and "exceeds Twitter limit" in validation['error']:
                logger.info(f"Video exceeds size limit, attempting compression")
                
                compressed_path = video_processor.compress_video(download_path)
                if compressed_path:
                    logger.info(f"Successfully compressed video: {compressed_path}")
                    # Validate the compressed video
                    new_validation = video_processor.validate_video(compressed_path)
                    if new_validation['valid']:
                        logger.info(f"Compressed video validation successful")
                        logger.info(f"New Duration: {new_validation['duration']:.2f}s, Size: {new_validation['size_bytes']/1024/1024:.2f}MB")
                    else:
                        logger.warning(f"Compressed video validation failed: {new_validation['error']}")
                else:
                    logger.error(f"Compression failed")
            
    except Exception as e:
        logger.exception(f"Error processing video: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_download_video.py <video_url> <video_id>")
        sys.exit(1)
    
    video_url = sys.argv[1]
    video_id = sys.argv[2]
    
    download_and_validate_video(video_url, video_id)
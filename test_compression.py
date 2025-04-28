import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import our modules
from bot.video_processor import VideoProcessor

def test_video_compression():
    """Test compressing a video"""
    
    # Check if a video path is provided
    if len(sys.argv) < 2:
        print("Usage: python test_compression.py <path_to_video_file>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    
    # Check if file exists
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        sys.exit(1)
    
    # Get file size
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    logger.info(f"Testing compression with video: {video_path} ({file_size_mb:.2f} MB)")
    
    try:
        # Initialize video processor
        logger.info("Initializing video processor...")
        video_processor = VideoProcessor()
        
        # First validate the video
        logger.info(f"Validating video: {video_path}")
        validation = video_processor.validate_video(video_path)
        
        if validation['valid']:
            logger.info(f"Video is valid: {validation}")
        else:
            logger.warning(f"Video validation failed: {validation['error']}")
            
            if "exceeds Twitter limit" in validation['error']:
                logger.info("Attempting to compress the video...")
                
                # Try compression
                compressed_path = video_processor.compress_video(video_path)
                
                if compressed_path:
                    compressed_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                    logger.info(f"Compression successful: {compressed_path} ({compressed_size_mb:.2f} MB)")
                    
                    # Validate the compressed video
                    compressed_validation = video_processor.validate_video(compressed_path)
                    logger.info(f"Compressed video validation: {compressed_validation}")
                else:
                    logger.error("Compression failed")
            else:
                logger.error("Video has issues other than size")
        
    except Exception as e:
        logger.exception(f"Error during compression test: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_video_compression()
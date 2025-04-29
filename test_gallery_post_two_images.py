"""
Test script for posting a gallery with exactly 2 images to Twitter as a thread
to verify our improved thread text formatting.
"""

import logging
import os
from datetime import datetime

from app import app, db
from models import Post
from bot.twitter_client import TwitterClient
from bot.video_processor import VideoProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
twitter_client = TwitterClient(use_mock=True)  # Use mock for this test
video_processor = VideoProcessor()

def test_two_image_gallery():
    """
    Test creating a Twitter thread with exactly 2 images
    to verify thread text formatting.
    """
    with app.app_context():
        try:
            logger.info("Testing gallery thread with exactly 2 images")
            
            # Create two test image paths (using existing images in the downloads folder)
            # For this test, we'll just use the same image twice
            image_paths = []
            
            # Find an existing image in the downloads folder
            for filename in os.listdir(video_processor.download_folder):
                if filename.endswith('.jpg'):
                    image_path = os.path.join(video_processor.download_folder, filename)
                    image_paths.append(image_path)
                    # We only need one existing image
                    break
            
            # If we found an image, duplicate it for the second one
            if image_paths:
                image_paths.append(image_paths[0])
            else:
                # If no image was found, create two dummy ones
                base_path = os.path.join(video_processor.download_folder, "test_gallery_image.jpg")
                
                # Create a simple black image if none exists
                import cv2
                import numpy as np
                test_image = np.zeros((100, 100, 3), dtype=np.uint8)
                cv2.imwrite(base_path, test_image)
                
                image_paths = [base_path, base_path]
            
            logger.info(f"Using images: {image_paths}")
            
            # Create post text
            post_text = "Test Gallery Post with Two Images [Gallery]"
            
            # Create continuation text
            continue_texts = []
            
            # Use the new standard format for all gallery images
            for i in range(1, len(image_paths)):
                continue_texts.append(f"Image {i+1}/{len(image_paths)}")
            
            # Create thread
            thread_result = twitter_client.create_thread_with_images(
                image_paths,
                main_text=post_text,
                continue_texts=continue_texts
            )
            
            if thread_result.get('success'):
                logger.info(f"Successfully created test thread with 2 images")
                logger.info(f"First tweet: {thread_result['first_tweet_url']}")
                logger.info(f"Continuation tweet text: {continue_texts[0]}")
            else:
                logger.error(f"Failed to create Twitter thread: {thread_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.exception(f"Error in test: {str(e)}")

if __name__ == "__main__":
    test_two_image_gallery()
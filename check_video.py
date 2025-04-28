import os
import cv2
import sys

def check_video(filepath):
    """Check video file and return information about it"""
    print(f"Checking video file: {filepath}")
    
    # Check if file exists
    if not os.path.exists(filepath):
        print(f"Error: File doesn't exist at {filepath}")
        return
    
    # Get file size
    size_bytes = os.path.getsize(filepath)
    size_mb = size_bytes / (1024 * 1024)
    print(f"File size: {size_bytes} bytes ({size_mb:.2f} MB)")
    
    try:
        # Open the video file
        video = cv2.VideoCapture(filepath)
        
        # Check if video opened successfully
        if not video.isOpened():
            print("Error: Could not open video file")
            return
        
        # Get video properties
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"Resolution: {width}x{height}")
        print(f"FPS: {fps:.2f}")
        print(f"Duration: {duration:.2f} seconds ({int(duration/60)}:{int(duration%60):02d})")
        print(f"Total frames: {frame_count}")
        
        # Release the video capture object
        video.release()
        
        print("Video file is valid")
        return True
    except Exception as e:
        print(f"Error analyzing video: {e}")
        return False

if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else "./downloads/1k8tcg7.mp4"
    check_video(filepath)
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import our Twitter client
from bot.twitter_client import TwitterClient

def test_twitter_auth():
    """Test Twitter API authentication only"""
    try:
        # Try to create a Twitter client
        logger.info("Testing Twitter API authentication...")
        twitter_client = TwitterClient(use_mock=False)
        
        # If we're using the mock client, authentication failed
        if twitter_client.use_mock:
            logger.error("Twitter authentication failed - see logs for details")
            return False
        
        logger.info("Twitter authentication successful!")
        return True
        
    except Exception as e:
        logger.exception(f"Unexpected error in test_twitter_auth: {e}")
        return False

if __name__ == "__main__":
    success = test_twitter_auth()
    if success:
        logger.info("✅ Twitter authentication test PASSED")
    else:
        logger.error("❌ Twitter authentication test FAILED")
        
    # Exit with appropriate code
    sys.exit(0 if success else 1)
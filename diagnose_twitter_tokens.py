import sys
import logging
import os
import tweepy
import json
import base64
import hmac
import hashlib
import urllib.parse
import time
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append('.')

# Import config to get credentials
from config import (
    TWITTER_API_KEY,
    TWITTER_API_KEY_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET
)

def check_token_format():
    """Check if the tokens have valid formats"""
    logger.info("Checking token formats...")
    
    # Check API key (typically 25 characters)
    if len(TWITTER_API_KEY) < 10:
        logger.error(f"API key seems too short: {len(TWITTER_API_KEY)} chars")
    else:
        logger.info(f"API key length looks reasonable: {len(TWITTER_API_KEY)} chars")
    
    # Check API key secret (typically 50 characters)
    if len(TWITTER_API_KEY_SECRET) < 10:
        logger.error(f"API key secret seems too short: {len(TWITTER_API_KEY_SECRET)} chars")
    else:
        logger.info(f"API key secret length looks reasonable: {len(TWITTER_API_KEY_SECRET)} chars")
    
    # Check access token (typically 50 characters)
    if len(TWITTER_ACCESS_TOKEN) < 10:
        logger.error(f"Access token seems too short: {len(TWITTER_ACCESS_TOKEN)} chars")
    else:
        logger.info(f"Access token length looks reasonable: {len(TWITTER_ACCESS_TOKEN)} chars")
    
    # Check access token secret (typically 45 characters)
    if len(TWITTER_ACCESS_TOKEN_SECRET) < 10:
        logger.error(f"Access token secret seems too short: {len(TWITTER_ACCESS_TOKEN_SECRET)} chars") 
    else:
        logger.info(f"Access token secret length looks reasonable: {len(TWITTER_ACCESS_TOKEN_SECRET)} chars")

def authenticate_with_v1():
    """Try authenticating with Twitter API v1.1"""
    logger.info("Testing authentication with Twitter API v1.1...")
    
    try:
        auth = tweepy.OAuth1UserHandler(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
        )
        api = tweepy.API(auth)
        
        # Test authentication by getting account information
        user = api.verify_credentials()
        logger.info(f"✅ Authentication successful! Authenticated as @{user.screen_name}")
        logger.info(f"Account created: {user.created_at}")
        logger.info(f"Account ID: {user.id}")
        logger.info(f"Friends count: {user.friends_count}")
        logger.info(f"Followers count: {user.followers_count}")
        
        return True
    except tweepy.TweepyException as e:
        logger.error(f"❌ Authentication failed: {str(e)}")
        return False

def authenticate_with_v2():
    """Try authenticating with Twitter API v2"""
    logger.info("Testing authentication with Twitter API v2...")
    
    try:
        client = tweepy.Client(
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_KEY_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
        )
        
        me = client.get_me()
        if me.data:
            logger.info(f"✅ API v2 authentication successful! User ID: {me.data.id}")
            logger.info(f"Username: @{me.data.username}")
            logger.info(f"Name: {me.data.name}")
            return True
        else:
            logger.error("❌ API v2 authentication failed: No user data returned")
            return False
    except Exception as e:
        logger.error(f"❌ API v2 authentication failed: {str(e)}")
        return False

def make_oauth_request():
    """Try making a raw OAuth 1.0a request to Twitter API"""
    logger.info("Testing direct OAuth 1.0a request...")
    
    # Generate OAuth parameters
    oauth_timestamp = str(int(time.time()))
    oauth_nonce = base64.b64encode(str(oauth_timestamp).encode()).decode()
    
    # Build the OAuth header
    oauth_params = {
        'oauth_consumer_key': TWITTER_API_KEY,
        'oauth_nonce': oauth_nonce,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': oauth_timestamp,
        'oauth_token': TWITTER_ACCESS_TOKEN,
        'oauth_version': '1.0'
    }
    
    # Create base string
    base_url = 'https://api.twitter.com/1.1/account/verify_credentials.json'
    method = 'GET'
    params_str = '&'.join(f"{k}={urllib.parse.quote(v)}" for k, v in sorted(oauth_params.items()))
    base_string = f"{method}&{urllib.parse.quote(base_url, safe='')}&{urllib.parse.quote(params_str, safe='')}"
    
    # Create signature
    signing_key = f"{urllib.parse.quote(TWITTER_API_KEY_SECRET, safe='')}&{urllib.parse.quote(TWITTER_ACCESS_TOKEN_SECRET, safe='')}"
    signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()
    
    # Add signature to parameters
    oauth_params['oauth_signature'] = signature
    
    # Create Authorization header
    auth_header = 'OAuth ' + ', '.join(f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"' for k, v in oauth_params.items())
    
    # Make the request
    headers = {
        'Authorization': auth_header
    }
    response = requests.get(base_url, headers=headers)
    
    if response.status_code == 200:
        user_data = response.json()
        logger.info(f"✅ Direct OAuth request successful! Authenticated as @{user_data.get('screen_name')}")
        return True
    else:
        logger.error(f"❌ Direct OAuth request failed: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("Twitter API Authentication Diagnostic Tool")
    print("=" * 80)
    
    # Check token format
    check_token_format()
    print("-" * 80)
    
    # Try with API v1.1
    v1_success = authenticate_with_v1()
    print("-" * 80)
    
    # Try with API v2
    v2_success = authenticate_with_v2()
    print("-" * 80)
    
    # Try direct OAuth
    oauth_success = make_oauth_request()
    print("-" * 80)
    
    # Summary
    print("\nResults Summary:")
    print(f"API v1.1 Authentication: {'✅ SUCCESS' if v1_success else '❌ FAILED'}")
    print(f"API v2 Authentication:   {'✅ SUCCESS' if v2_success else '❌ FAILED'}")
    print(f"Direct OAuth Request:    {'✅ SUCCESS' if oauth_success else '❌ FAILED'}")
    
    if not (v1_success or v2_success or oauth_success):
        print("\nRecommendations:")
        print("1. Regenerate your API keys and access tokens in the Twitter Developer Portal")
        print("2. Make sure your app has the right permissions (read/write)")
        print("3. Check that your app has elevated access if you need it")
        print("4. Ensure you're using keys/tokens from the same application")
        print("5. Verify that the Twitter API isn't experiencing downtime")
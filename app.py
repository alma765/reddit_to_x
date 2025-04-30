import os
import logging
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1) # needed for url_for to generate with https

# configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///redditbot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
# initialize the app with the extension, flask-sqlalchemy >= 3.0.x
db.init_app(app)

with app.app_context():
    # Make sure to import the models here or their tables won't be created
    import models  # noqa: F401
    db.create_all()

from bot.scheduler import scheduler
from config import SUBREDDITS, POST_INTERVAL_MINUTES, REDDIT_CLIENT_ID, TWITTER_API_KEY

@app.route('/')
def index():
    """Homepage displaying bot status and configuration"""
    from models import Post
    from bot.twitter_client import TwitterClient
    
    # Get basic stats
    total_posts = db.session.query(Post).count()
    successful_posts = db.session.query(Post).filter_by(posted_to_twitter=True).count()
    failed_posts = db.session.query(Post).filter_by(error=True).count()
    duplicate_posts = db.session.query(Post).filter(Post.error_message.like('%Duplicate%')).count()
    
    # Get content type stats
    video_posts = db.session.query(Post).filter_by(content_type='video').count()
    image_posts = db.session.query(Post).filter_by(content_type='image').count()
    
    # Get latest posts
    latest_posts = db.session.query(Post).order_by(Post.created_at.desc()).limit(5).all()
    
    # Check API configuration status
    reddit_configured = bool(REDDIT_CLIENT_ID)
    twitter_configured = bool(TWITTER_API_KEY)
    
    # Get persistent Twitter rate limit status
    from models import SystemStatus
    
    # First check stored rate limit status
    twitter_rate_limited = SystemStatus.get_bool('twitter_rate_limited', False)
    rate_limit_until = SystemStatus.get_str('twitter_rate_limit_until', None)
    
    # Check if we need to clear the rate limit status
    if rate_limit_until:
        try:
            rate_limit_time = datetime.fromisoformat(rate_limit_until)
            if datetime.utcnow() > rate_limit_time:
                # Rate limit period has passed, clear the flag
                SystemStatus.set_bool('twitter_rate_limited', False)
                SystemStatus.set_str('twitter_rate_limit_until', None)
                twitter_rate_limited = False
                logger.info("Twitter rate limit period has expired, cleared the flag")
        except Exception as e:
            logger.error(f"Error parsing rate limit time: {e}")
    
    # Also check for Twitter rate limiting by looking at recent errors (as backup)
    rate_limit_errors = db.session.query(Post).filter(
        (Post.error_message.like('%429%') | 
        Post.error_message.like('%Too Many Requests%') |
        Post.error_message.like('%rate limit%')) &
        # Only check errors from the last hour
        (Post.processed_at > (datetime.utcnow() - timedelta(hours=1)))
    ).count()
    
    # If we have any recent rate limit errors, consider Twitter rate limited
    if rate_limit_errors > 0 and not twitter_rate_limited:
        twitter_rate_limited = True
        # Store this status
        SystemStatus.set_bool('twitter_rate_limited', True)
        # Set rate limit expiration time to 1 hour from now if not already set
        if not rate_limit_until:
            one_hour_later = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            SystemStatus.set_str('twitter_rate_limit_until', one_hour_later)
            logger.warning(f"Setting Twitter rate limit until: {one_hour_later}")
    
    # Only check Twitter status if we're not already rate limited
    # This avoids unnecessary API calls which could quickly exhaust our 100 requests/day limit
    if not twitter_rate_limited and twitter_configured:
        # Check when we last made a Twitter status check to avoid too many calls
        last_check_time_str = SystemStatus.get_str('last_twitter_status_check', None)
        should_check = True
        
        if last_check_time_str:
            try:
                last_check_time = datetime.fromisoformat(last_check_time_str)
                # Only check once per hour to limit API calls
                if (datetime.utcnow() - last_check_time).total_seconds() < 3600:  # 1 hour
                    should_check = False
                    logger.info(f"Skipping Twitter status check - last checked at {last_check_time_str}")
            except Exception:
                pass
        
        if should_check:
            try:
                # Record that we're making a status check
                SystemStatus.set_str('last_twitter_status_check', datetime.utcnow().isoformat())
                
                # Make a test Twitter client
                test_client = TwitterClient()
                # Check if Twitter API is currently rate limited - THIS MAKES AN API CALL
                rate_limited = test_client.is_rate_limited()
                
                if rate_limited:
                    twitter_rate_limited = True
                    # Store this status
                    SystemStatus.set_bool('twitter_rate_limited', True)
                    
                    # Check if we have the actual reset time from Twitter's API
                    if isinstance(rate_limited, tuple) and len(rate_limited) > 1:
                        reset_time = rate_limited[1]  # This is an ISO format datetime string
                        SystemStatus.set_str('twitter_rate_limit_until', reset_time)
                        logger.warning(f"Twitter rate limit detected - Will reset at: {reset_time}")
                    else:
                        # Default to 24 hours for Twitter's 100 requests/day limit
                        day_later = (datetime.utcnow() + timedelta(hours=24)).isoformat()
                        SystemStatus.set_str('twitter_rate_limit_until', day_later)
                        logger.warning(f"Twitter rate limit detected - Using default 24-hour expiration: {day_later}")
            except Exception as e:
                logger.error(f"Error checking Twitter status: {e}")
                # If we get an exception that contains rate limit errors, mark as rate limited
                error_str = str(e).lower()
                if "429" in error_str or "too many requests" in error_str or "rate limit" in error_str:
                    twitter_rate_limited = True
                    # Store this status
                    SystemStatus.set_bool('twitter_rate_limited', True)
                    
                    # Default to 24 hours for Twitter's 100 requests/day limit
                    reset_time = (datetime.utcnow() + timedelta(hours=24)).isoformat()
                    SystemStatus.set_str('twitter_rate_limit_until', reset_time)
                    logger.warning(f"Twitter daily rate limit reached - Using 24-hour expiration: {reset_time}")
    elif twitter_rate_limited:
        logger.info("Twitter is currently rate limited - skipping status check to avoid unnecessary API calls")
    
    return render_template('index.html', 
                          total_posts=total_posts,
                          successful_posts=successful_posts,
                          failed_posts=failed_posts,
                          duplicate_posts=duplicate_posts,
                          twitter_rate_limited=twitter_rate_limited,
                          video_posts=video_posts,
                          image_posts=image_posts,
                          latest_posts=latest_posts,
                          subreddits=SUBREDDITS,
                          post_interval=POST_INTERVAL_MINUTES,
                          scheduler_running=scheduler.running,
                          reddit_configured=reddit_configured,
                          twitter_configured=twitter_configured)

@app.route('/logs')
def logs():
    """View detailed logs of all posts"""
    from models import Post
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filtering options
    filter_type = request.args.get('filter', 'all')
    subreddit = request.args.get('subreddit', '')
    content_type = request.args.get('content_type', '')
    
    query = db.session.query(Post)
    
    if filter_type == 'success':
        query = query.filter_by(posted_to_twitter=True)
    elif filter_type == 'failed':
        query = query.filter_by(error=True)
    elif filter_type == 'duplicates':
        query = query.filter(Post.error_message.like('%Duplicate%'))
    elif filter_type == 'pending':
        query = query.filter_by(posted_to_twitter=False, error=False)
    elif filter_type == 'videos':
        query = query.filter_by(content_type='video')
    elif filter_type == 'images':
        query = query.filter_by(content_type='image')
        
    if subreddit:
        query = query.filter_by(subreddit=subreddit)
        
    if content_type and filter_type not in ['videos', 'images']:
        query = query.filter_by(content_type=content_type)
    
    # Get paginated results
    pagination = query.order_by(Post.created_at.desc()).paginate(page=page, per_page=per_page)
    posts = pagination.items
    
    # Get list of all subreddits for filter dropdown
    all_subreddits = db.session.query(Post.subreddit).distinct().all()
    all_subreddits = [s[0] for s in all_subreddits]
    
    return render_template('logs.html', 
                          posts=posts, 
                          pagination=pagination,
                          all_subreddits=all_subreddits,
                          current_filter=filter_type,
                          current_subreddit=subreddit)

@app.route('/api/status')
def api_status():
    """JSON endpoint for status checks"""
    from models import Post
    
    try:
        total_posts = db.session.query(Post).count()
        successful_posts = db.session.query(Post).filter_by(posted_to_twitter=True).count()
        failed_posts = db.session.query(Post).filter_by(error=True).count()
        duplicate_posts = db.session.query(Post).filter(Post.error_message.like('%Duplicate%')).count()
        in_progress = total_posts - successful_posts - failed_posts
        
        # Content type stats
        video_posts = db.session.query(Post).filter_by(content_type='video').count()
        image_posts = db.session.query(Post).filter_by(content_type='image').count()
        
        # Success rate by content type
        video_success = db.session.query(Post).filter_by(content_type='video', posted_to_twitter=True).count()
        image_success = db.session.query(Post).filter_by(content_type='image', posted_to_twitter=True).count()
        
        # Check for Twitter rate limit status using the persistent flag
        from models import SystemStatus
        twitter_rate_limited = SystemStatus.get_bool('twitter_rate_limited', False)
        rate_limit_until = SystemStatus.get_str('twitter_rate_limit_until', None)
        
        # Add expiration time to the response if available
        rate_limit_expiration = None
        if rate_limit_until:
            try:
                rate_limit_time = datetime.fromisoformat(rate_limit_until)
                # Only include if it's in the future
                if rate_limit_time > datetime.utcnow():
                    rate_limit_expiration = rate_limit_until
            except Exception:
                pass
        
        response_data = {
            'status': 'running' if scheduler.running else 'stopped',
            'total_posts': total_posts,
            'successful_posts': successful_posts,
            'failed_posts': failed_posts,
            'duplicate_posts': duplicate_posts,
            'error_posts': failed_posts - duplicate_posts,
            'twitter_rate_limited': twitter_rate_limited,
            'in_progress': in_progress,
            'success_rate': (successful_posts / total_posts * 100) if total_posts > 0 else 0,
            'content_types': {
                'video': {
                    'total': video_posts,
                    'successful': video_success,
                    'success_rate': (video_success / video_posts * 100) if video_posts > 0 else 0
                },
                'image': {
                    'total': image_posts,
                    'successful': image_success,
                    'success_rate': (image_success / image_posts * 100) if image_posts > 0 else 0
                }
            }
        }
        
        # Add rate limit expiration time if available
        if rate_limit_expiration:
            try:
                expiry_time = datetime.fromisoformat(rate_limit_expiration)
                now = datetime.utcnow()
                minutes_remaining = int((expiry_time - now).total_seconds() / 60)
                
                response_data['twitter_rate_limit_info'] = {
                    'expiration': rate_limit_expiration,
                    'minutes_remaining': max(0, minutes_remaining),
                    'human_readable': f"Rate limited for {max(0, minutes_remaining)} more minutes"
                }
            except Exception as e:
                logger.error(f"Error calculating rate limit expiration: {e}")
                
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error in API status: {str(e)}")
        return jsonify({
            'status': 'unknown',
            'total_posts': 0,
            'successful_posts': 0,
            'failed_posts': 0,
            'duplicate_posts': 0,
            'error_posts': 0,
            'in_progress': 0,
            'success_rate': 0,
            'twitter_rate_limited': False,
            'error': str(e)
        }), 500

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    """Start the bot scheduler"""
    if not scheduler.running:
        try:
            scheduler.start()
            flash('Bot scheduler started successfully', 'success')
        except Exception as e:
            flash(f'Failed to start scheduler: {str(e)}', 'danger')
    else:
        flash('Scheduler is already running', 'info')
    return redirect(url_for('index'))

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    """Stop the bot scheduler"""
    if scheduler.running:
        try:
            scheduler.shutdown()
            flash('Bot scheduler stopped successfully', 'success')
        except Exception as e:
            flash(f'Failed to stop scheduler: {str(e)}', 'danger')
    else:
        flash('Scheduler is already stopped', 'info')
    return redirect(url_for('index'))

def clean_duplicate_entries():
    """
    Remove existing duplicate entries that were never posted to Twitter.
    A true duplicate should be content that was successfully posted to Twitter.
    """
    from models import Post
    
    # Find all entries marked as duplicates that were never posted to Twitter
    fake_duplicates = Post.query.filter(
        Post.error == True,
        Post.error_message.like("%Duplicate%"),
        Post.posted_to_twitter == False
    ).all()
    
    logger.info(f"Found {len(fake_duplicates)} 'duplicate' entries that were never posted to Twitter")
    
    # Delete these entries
    for post in fake_duplicates:
        logger.info(f"Deleting fake duplicate entry: {post.reddit_id} - {post.title}")
        db.session.delete(post)
    
    # Commit changes
    db.session.commit()
    logger.info(f"Successfully cleaned up {len(fake_duplicates)} fake duplicate entries")
    
    return len(fake_duplicates)

@app.route('/api/run_now', methods=['POST'])
def run_now():
    """Run the bot once immediately via a one-time job"""
    from bot.scheduler import scheduler, process_and_post
    from datetime import datetime, timedelta
    
    try:
        # First clean up any mock Twitter records in this request
        cleanup_mock_twitter_records()
        
        # Clean up any fake duplicate entries in this request
        clean_duplicate_entries()
        
        # Schedule the processing to run immediately as a one-time job
        # This prevents the request from timing out during long-running operations
        job_id = 'manual_run_' + datetime.now().strftime('%Y%m%d%H%M%S')
        scheduler.add_job(
            process_and_post,
            'date',
            run_date=datetime.now() + timedelta(seconds=5),  # Run 5 seconds after this request completes
            id=job_id
        )
        flash('Bot scheduled to run in a few seconds', 'success')
        logger.info(f"Manual bot run scheduled with job ID: {job_id}")
    except Exception as e:
        logger.exception("Error scheduling bot to run manually")
        flash(f'Error scheduling bot: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/api/cleanup_duplicates', methods=['POST'])
def cleanup_duplicates():
    """Clean up fake duplicate entries from the database"""
    try:
        num_cleaned = clean_duplicate_entries()
        flash(f'Successfully cleaned up {num_cleaned} fake duplicate entries', 'success')
    except Exception as e:
        logger.exception("Error cleaning up duplicate entries")
        flash(f'Error cleaning up duplicate entries: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

def cleanup_mock_twitter_records():
    """
    Check for and clean up any mock Twitter records in the database
    This function fixes records that show a post was successful but actually failed due to rate limits
    """
    from models import Post
    import re
    
    try:
        # Find posts with suspicious Twitter IDs (non-numeric or starting with 'c', 'mock', etc.)
        suspect_records = db.session.query(Post).filter(
            (Post.posted_to_twitter == True) & 
            (
                (Post.twitter_post_id.op('~')('^[a-zA-Z]')) |  # Starts with letter
                (Post.twitter_post_id.like('mock%')) |         # Starts with "mock"
                (Post.twitter_post_id.like('c%'))              # Starts with "c"
            )
        ).all()
        
        count = 0
        for post in suspect_records:
            logger.warning(f"Found suspicious Twitter post record: ID {post.id}, Reddit ID {post.reddit_id}, Twitter ID {post.twitter_post_id}")
            
            # Update the record to show it properly failed
            post.posted_to_twitter = False
            post.twitter_post_id = None
            post.twitter_post_url = None
            post.error = True
            post.error_message = "Twitter rate limit reached. Will retry later."
            
            db.session.add(post)
            count += 1
            
        if count > 0:
            db.session.commit()
            logger.info(f"Cleaned up {count} mock Twitter records")
            
    except Exception as e:
        logger.exception(f"Error cleaning up mock Twitter records: {str(e)}")
        # Don't reraise - this is a cleanup function and shouldn't stop main execution

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

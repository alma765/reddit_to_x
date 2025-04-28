from datetime import datetime
from app import db

class Post(db.Model):
    """Model for tracking Reddit posts processed by the bot"""
    id = db.Column(db.Integer, primary_key=True)
    reddit_id = db.Column(db.String(20), unique=True, nullable=False)
    reddit_url = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    cleaned_title = db.Column(db.String(300), nullable=True)  # Stores the cleaned title
    subreddit = db.Column(db.String(50), nullable=False)
    author = db.Column(db.String(50), nullable=True)
    video_path = db.Column(db.String(255), nullable=True)
    video_size_bytes = db.Column(db.Integer, nullable=True)
    video_duration_seconds = db.Column(db.Float, nullable=True)
    
    posted_to_twitter = db.Column(db.Boolean, default=False)
    twitter_post_id = db.Column(db.String(50), nullable=True)
    twitter_post_url = db.Column(db.String(255), nullable=True)
    
    error = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Post {self.reddit_id}>'

    def to_dict(self):
        """Convert object to dictionary for easy serialization"""
        return {
            'id': self.id,
            'reddit_id': self.reddit_id,
            'reddit_url': self.reddit_url,
            'title': self.title,
            'cleaned_title': self.cleaned_title,
            'subreddit': self.subreddit,
            'author': self.author,
            'video_path': self.video_path,
            'video_size_bytes': self.video_size_bytes,
            'video_duration_seconds': self.video_duration_seconds,
            'posted_to_twitter': self.posted_to_twitter,
            'twitter_post_id': self.twitter_post_id,
            'twitter_post_url': self.twitter_post_url,
            'error': self.error,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }

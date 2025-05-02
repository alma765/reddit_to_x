from app import app, db
from models import SystemStatus, Post

with app.app_context():
    # Drop all tables first to ensure a clean state
    db.drop_all()
    
    # Create all tables
    db.create_all()
    
    # Initialize default system status values
    SystemStatus.set_bool('bot_running', False)
    SystemStatus.set_bool('bot_enabled', True)
    SystemStatus.set_bool('cleaning_duplicates', False)
    
    print("Database initialized successfully!")

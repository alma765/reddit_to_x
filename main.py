from app import app  # noqa: F401
from bot.scheduler import scheduler

# Start the scheduler when the application starts
if __name__ == '__main__':
    scheduler.start()
    app.run(host='0.0.0.0', port=5000, debug=True)

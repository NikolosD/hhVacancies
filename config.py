import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Search settings
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "Frontend React")
CHECK_INTERVAL_SECONDS = 600  # Check every 10 minutes

# Target Chat ID
TARGET_CHAT_ID = None 

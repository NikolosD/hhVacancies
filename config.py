import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Search settings
# Supports multiple queries separated by comma: "Frontend React, Vue developer, TypeScript"
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "Frontend React")
SEARCH_QUERIES = [q.strip() for q in SEARCH_QUERY.split(",") if q.strip()]

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))

# Filters
MIN_SALARY = int(os.getenv("MIN_SALARY", "0"))  # Minimum salary filter (0 = disabled)
EXPERIENCE = os.getenv("EXPERIENCE", "")  # noExperience, between1And3, between3And6, moreThan6
AREA = os.getenv("AREA", "113")  # 113 = Russia, 1 = Moscow, 2 = St. Petersburg, "" = worldwide

# Remote only mode: set to "true" to only show remote jobs
REMOTE_ONLY = os.getenv("REMOTE_ONLY", "").lower() == "true"

# Schedule filter for remote work
SCHEDULE = "remote" if REMOTE_ONLY else ""

# Target Chat ID
TARGET_CHAT_ID = None


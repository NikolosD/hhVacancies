# Job Searching Bot for Telegram

This bot monitors HH.ru for vacancies and reposts them to a Telegram chat.

## Features
- Search by keywords (default: "Frontend React")
- Filter by date (newest first)
- Deduplication (uses SQLite)
- Railway-ready

## Setup
1. Clone the repo.
2. Create `.env` file with:
   ```
   BOT_TOKEN=your_token
   SEARCH_QUERY=Frontend React
   ```
3. Run `python main.py`

## Deploy to Railway
See `DEPLOY_RAILWAY.md`.

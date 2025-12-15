# Job Search Telegram Bot

Monitors HH.ru for vacancies and posts them to Telegram with interactive buttons.

## Features
- 🔍 **Multiple search queries** (comma-separated)
- 💰 **Salary filter**
- 📊 **Experience filter** (junior/middle/senior)
- 🏠 **Remote only mode**
- ⭐ **Favorites** - save interesting vacancies
- 🙈 **Hide** - hide irrelevant vacancies
- ⚡ **Force check** with `/jobs` command

## Commands
- `/start` - Show settings
- `/jobs` - Check vacancies now
- `/favorites` - Show saved vacancies

## Configuration (Environment Variables)

| Variable | Description | Example |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token | `123456:ABC...` |
| `SEARCH_QUERY` | Search queries (comma-separated) | `Frontend React, Vue developer` |
| `MIN_SALARY` | Minimum salary filter | `150000` |
| `EXPERIENCE` | Experience level | `noExperience`, `between1And3`, `between3And6`, `moreThan6` |
| `AREA` | HH.ru area ID | `113` (Russia), `1` (Moscow), `2` (SPb) |
| `REMOTE_ONLY` | Only remote jobs | `true` / `false` |
| `CHECK_INTERVAL_SECONDS` | Check interval | `600` (10 min) |

## Local Setup
```bash
pip install -r requirements.txt
# Create .env with your settings
python main.py
```

## Deploy to Railway
See [DEPLOY_RAILWAY.md](./DEPLOY_RAILWAY.md)

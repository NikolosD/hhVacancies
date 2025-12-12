import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import BadRequest

import config
import storage
import hh_client

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to store chat_id (in a real app, use DB)
# For this simple version, we'll store the last chat that interacted with the bot
# or we can ask user to explicitly set it.
target_chat_id = config.TARGET_CHAT_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and saves the chat ID."""
    global target_chat_id
    chat = update.effective_chat
    target_chat_id = chat.id
    
    msg = (
        f"Привет! Я бот для поиска вакансий.\n"
        f"Я буду искать: <b>{config.SEARCH_QUERY}</b>\n"
        f"И скидывать новые вакансии в этот чат ({chat.id}).\n"
        f"Проверка каждые {config.CHECK_INTERVAL_SECONDS / 60} минут."
    )
    await update.message.reply_html(msg)
    logger.info(f"Target chat set to {target_chat_id}")

    # Immediately check for vacancies
    await check_vacancies(context)


async def check_vacancies(context: ContextTypes.DEFAULT_TYPE):
    """Background task to check for new vacancies."""
    global target_chat_id
    if not target_chat_id:
        logger.warning("No target chat set yet. Waiting for /start command.")
        return

    logger.info("Checking for new vacancies...")
    vacancies = await hh_client.get_vacancies(config.SEARCH_QUERY)
    
    new_count = 0
    for vac in reversed(vacancies): # Process correctly sent order if we send 1 by 1
        vac_id = vac.get("id")
        if not vac_id:
            continue
            
        if not storage.is_sent(vac_id):
            text = hh_client.format_vacancy(vac)
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=text, parse_mode="HTML")
                storage.mark_sent(vac_id)
                new_count += 1
                # Small delay to avoid hitting telegram limits
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    if new_count > 0:
        logger.info(f"Sent {new_count} new vacancies.")
    else:
        logger.info("No new vacancies found.")


def main():
    """Start the bot."""
    storage.init_db()
    
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    
    # Add job queue
    job_queue = application.job_queue
    job_queue.run_repeating(check_vacancies, interval=config.CHECK_INTERVAL_SECONDS, first=10)

    logger.info("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()

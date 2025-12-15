import logging
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
target_chat_id = config.TARGET_CHAT_ID

# In-memory cache for vacancy data (for button callbacks)
vacancy_cache = {}


def build_vacancy_keyboard(vacancy_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for a vacancy."""
    is_fav = storage.is_favorite(vacancy_id)
    fav_text = "⭐ Убрать" if is_fav else "⭐ В избранное"
    
    keyboard = [
        [
            InlineKeyboardButton(fav_text, callback_data=f"fav:{vacancy_id}"),
            InlineKeyboardButton("❌ Скрыть", callback_data=f"hide:{vacancy_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and saves the chat ID."""
    global target_chat_id
    chat = update.effective_chat
    target_chat_id = chat.id
    
    # Build settings info
    queries_str = ", ".join(getattr(config, 'SEARCH_QUERIES', [config.SEARCH_QUERY]))
    settings_lines = [
        f"🔍 <b>Поиск:</b> {queries_str}",
        f"⏱ <b>Интервал:</b> {config.CHECK_INTERVAL_SECONDS // 60} мин",
    ]
    if config.MIN_SALARY > 0:
        settings_lines.append(f"💰 <b>Мин. зарплата:</b> {config.MIN_SALARY:,}".replace(",", " "))
    if config.EXPERIENCE:
        exp_map = {
            "noExperience": "Без опыта",
            "between1And3": "1-3 года",
            "between3And6": "3-6 лет",
            "moreThan6": "6+ лет"
        }
        settings_lines.append(f"📊 <b>Опыт:</b> {exp_map.get(config.EXPERIENCE, config.EXPERIENCE)}")
    if getattr(config, 'REMOTE_ONLY', False):
        settings_lines.append("🏠 <b>Режим:</b> Только удаленка")
    
    settings_str = "\n".join(settings_lines)
    
    msg = (
        f"👋 Привет! Я бот для поиска вакансий.\n\n"
        f"{settings_str}\n\n"
        f"📌 Этот чат ({chat.id}) будет получать новые вакансии.\n\n"
        f"<b>Команды:</b>\n"
        f"/jobs — проверить вакансии сейчас\n"
        f"/favorites — показать избранное\n"
        f"/start — показать настройки"
    )
    await update.message.reply_html(msg)
    logger.info(f"Target chat set to {target_chat_id}")

    # Immediately check for vacancies
    await check_vacancies(context)


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force check for new vacancies."""
    global target_chat_id
    chat = update.effective_chat
    target_chat_id = chat.id
    
    await update.message.reply_text("🔄 Проверяю новые вакансии...")
    await check_vacancies(context)


async def favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show saved favorites."""
    favs = storage.get_favorites()
    
    if not favs:
        await update.message.reply_text("⭐ У вас пока нет избранных вакансий.")
        return
    
    msg_lines = ["⭐ <b>Избранные вакансии:</b>\n"]
    for i, fav in enumerate(favs[:20], 1):  # Limit to 20
        title = fav["title"]
        url = fav["url"]
        employer = fav["employer"]
        salary = fav["salary"] or "Не указана"
        msg_lines.append(f"{i}. <b>{title}</b>\n   🏢 {employer} | 💰 {salary}\n   🔗 {url}\n")
    
    await update.message.reply_html("\n".join(msg_lines))


async def check_vacancies(context: ContextTypes.DEFAULT_TYPE):
    """Background task to check for new vacancies."""
    global target_chat_id
    if not target_chat_id:
        logger.warning("No target chat set yet. Waiting for /start command.")
        return

    logger.info("Checking for new vacancies...")
    
    # Iterate over all search queries
    queries = getattr(config, 'SEARCH_QUERIES', [config.SEARCH_QUERY])
    
    new_count = 0
    for query in queries:
        vacancies = await hh_client.get_vacancies(text=query)
        
        for vac in reversed(vacancies):
            vac_id = vac.get("id")
            if not vac_id:
                continue
            
            # Skip hidden vacancies
            if storage.is_hidden(vac_id):
                continue
                
            if not storage.is_sent(vac_id):
                # Cache vacancy for button callbacks
                vacancy_cache[vac_id] = vac
                
                text = hh_client.format_vacancy(vac)
                keyboard = build_vacancy_keyboard(vac_id)
                
                try:
                    await context.bot.send_message(
                        chat_id=target_chat_id, 
                        text=text, 
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    storage.mark_sent(vac_id)
                    new_count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")

    if new_count > 0:
        logger.info(f"Sent {new_count} new vacancies.")
    else:
        logger.info("No new vacancies found.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data:
        return
    
    action, vacancy_id = data.split(":", 1)
    
    if action == "fav":
        # Toggle favorite
        if storage.is_favorite(vacancy_id):
            storage.remove_favorite(vacancy_id)
            await query.answer("❌ Убрано из избранного")
        else:
            # Get vacancy from cache or create minimal entry
            vacancy = vacancy_cache.get(vacancy_id, {"id": vacancy_id})
            storage.add_favorite(vacancy)
            await query.answer("⭐ Добавлено в избранное!")
        
        # Update keyboard
        try:
            new_keyboard = build_vacancy_keyboard(vacancy_id)
            await query.edit_message_reply_markup(reply_markup=new_keyboard)
        except BadRequest:
            pass  # Message might be too old
    
    elif action == "hide":
        storage.hide_vacancy(vacancy_id)
        await query.answer("🙈 Вакансия скрыта")
        
        # Remove message or mark as hidden
        try:
            await query.edit_message_text(
                text="<i>🙈 Вакансия скрыта</i>",
                parse_mode="HTML"
            )
        except BadRequest:
            pass


def main():
    """Start the bot."""
    storage.init_db()
    
    # Debug token presence
    if not config.BOT_TOKEN:
        logger.error("CRITICAL: BOT_TOKEN is missing or empty!")
    else:
        logger.info(f"Token found. Length: {len(config.BOT_TOKEN)}")

    application = Application.builder().token(config.BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("jobs", jobs))
    application.add_handler(CommandHandler("favorites", favorites))
    
    # Button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Job queue for periodic checks
    job_queue = application.job_queue
    job_queue.run_repeating(check_vacancies, interval=config.CHECK_INTERVAL_SECONDS, first=10)

    logger.info("Bot started...")
    application.run_polling()


if __name__ == "__main__":
    main()

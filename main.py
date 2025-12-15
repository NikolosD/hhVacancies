import logging
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

import config
import storage
import hh_client
import ai_filter

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
        f"/jobs — проверить вакансии\n"
        f"/favorites — избранное\n"
        f"/settings — настройки\n"
        f"/stats — статистика"
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
    
    msg = await update.message.reply_text("🔄 Проверяю вакансии...")
    new_count = await check_vacancies(context, return_count=True)
    
    if new_count == 0:
        # Show latest vacancies IF they haven't been sent yet
        await msg.edit_text("🔍 Новых нет, ищу пропущенные...")
        shown = await show_latest_vacancies(context, limit=5)
        if shown == 0:
            await msg.edit_text("✅ Все актуальные вакансии уже были отправлены. Отдыхайте! ☕")
        else:
            await context.bot.send_message(chat_id=target_chat_id, text=f"👆 Найдено {shown} пропущенных вакансий")
    else:
        await msg.edit_text(f"✅ Найдено {new_count} новых вакансий!")


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


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics and analytics."""
    weekly = storage.get_weekly_stats()
    total_sent = storage.get_total_sent_count()
    favorites_count = storage.get_favorites_count()
    
    lines = [
        "📊 <b>Статистика бота</b>\n",
        f"📈 Всего отправлено: {total_sent}",
        f"⭐ В избранном: {favorites_count}",
        "",
        "<b>За последние 7 дней:</b>",
        f"📋 Новых вакансий: {weekly['total_vacancies']}",
    ]
    
    if weekly['avg_salary'] > 0:
        lines.append(f"💰 Средняя зарплата: {weekly['avg_salary']:,} ₽".replace(",", " "))
    
    # By query
    if weekly['by_query']:
        lines.append("\n<b>По запросам:</b>")
        for q in weekly['by_query'][:5]:
            sal_str = f" ({q['avg_salary']:,}₽)".replace(",", " ") if q['avg_salary'] else ""
            lines.append(f"• {q['query']}: {q['count']} вакансий{sal_str}")
    
    # Daily trend (simple text graph)
    if weekly['daily']:
        lines.append("\n<b>По дням:</b>")
        max_count = max(d['count'] for d in weekly['daily']) or 1
        for d in weekly['daily'][-7:]:
            bar_len = int((d['count'] / max_count) * 10)
            bar = "▓" * bar_len + "░" * (10 - bar_len)
            lines.append(f"{d['date'][-5:]}: {bar} {d['count']}")
    
    await update.message.reply_html("\n".join(lines))


def build_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Build inline keyboard for settings menu."""
    settings = storage.get_chat_settings(chat_id)
    
    remote_text = "🏠 Удаленка: ✅" if settings["remote_only"] else "🏠 Удаленка: ❌"
    
    keyboard = [
        [InlineKeyboardButton("🔍 Запрос", callback_data="set:query"), 
         InlineKeyboardButton("💰 Зарплата", callback_data="set:salary")],
        [InlineKeyboardButton("📊 Опыт", callback_data="set:exp"),
         InlineKeyboardButton("🏠 Удаленка", callback_data="set:remote")],
        [InlineKeyboardButton("🌊 Глубина поиска", callback_data="set:depth")],
        [InlineKeyboardButton("✅ Готово", callback_data="set:done")]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_experience_keyboard() -> InlineKeyboardMarkup:
    """Build keyboard for experience selection."""
    keyboard = [
        [InlineKeyboardButton("👶 Без опыта", callback_data="exp:noExperience")],
        [InlineKeyboardButton("👨‍💻 1-3 года", callback_data="exp:between1And3")],
        [InlineKeyboardButton("👨‍🔧 3-6 лет", callback_data="exp:between3And6")],
        [InlineKeyboardButton("👴 6+ лет", callback_data="exp:moreThan6")],
        [InlineKeyboardButton("🔄 Любой", callback_data="exp:")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="set:back")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu with inline buttons."""
    chat = update.effective_chat
    chat_settings = storage.get_chat_settings(chat.id)
    
    exp_map = {
        "noExperience": "Без опыта",
        "between1And3": "1-3 года",
        "between3And6": "3-6 лет",
        "moreThan6": "6+ лет",
        "": "Любой"
    }
    
    msg = (
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"🔍 <b>Поиск:</b> {chat_settings['search_query']}\n"
        f"💰 <b>Мин. зарплата:</b> {chat_settings['min_salary']:,} ₽\n".replace(",", " ") +
        f"📊 <b>Опыт:</b> {exp_map.get(chat_settings['experience'], chat_settings['experience'])}\n"
        f"🏠 <b>Только удаленка:</b> {'Да' if chat_settings['remote_only'] else 'Нет'}\n"
        f"🌊 <b>Глубина поиска:</b> {chat_settings.get('search_depth', 1)} стр.\n\n"
        f"Нажмите кнопку, чтобы изменить настройку:"
    )
    
    keyboard = build_settings_keyboard(chat.id)
    await update.message.reply_html(msg, reply_markup=keyboard)


async def show_latest_vacancies(context: ContextTypes.DEFAULT_TYPE, limit: int = 5) -> int:
    """Show latest vacancies regardless of whether they were sent before."""
    global target_chat_id
    if not target_chat_id:
        return 0
    
    queries = getattr(config, 'SEARCH_QUERIES', [config.SEARCH_QUERY])
    shown = 0
    
    for query in queries:
        if shown >= limit:
            break
            
        # Get search depth from settings (default 1)
        depth = storage.get_chat_settings(target_chat_id).get("search_depth", 1)
        
        # Prepare list of NOT sent vacancies by iterating pages
        not_sent_vacancies = []
        
        # Always check page 0 first
        vacancies = await hh_client.get_vacancies(text=query, page=0)
        for vac in vacancies:
            vac_id = vac.get("id")
            if vac_id and not storage.is_sent(vac_id) and not storage.is_hidden(vac_id):
                not_sent_vacancies.append(vac)

        # If page 0 empty and depth > 1, check deeper pages
        if not not_sent_vacancies and depth > 1:
            await context.bot.send_message(chat_id=target_chat_id, text=f"🔎 На первой странице всё просмотрено, копаю глубже (до {depth} стр)...")
            
            for page in range(1, depth):
                # Stop if we found enough vacancies or hit limit
                if len(not_sent_vacancies) >= limit:
                    break
                    
                p_vacs = await hh_client.get_vacancies(text=query, page=page)
                if not p_vacs:
                    break # End of results
                    
                for vac in p_vacs:
                    vac_id = vac.get("id")
                    if vac_id and not storage.is_sent(vac_id) and not storage.is_hidden(vac_id):
                        not_sent_vacancies.append(vac)
                
                # Small delay to respect API limits
                await asyncio.sleep(0.3)
        
        # If we have unsent vacancies, show them
        if not_sent_vacancies:
            for vac in not_sent_vacancies[:limit - shown]:
                vac_id = vac.get("id")
                
                # AI Scoring
                ai_score = -1
                ai_reasoning = None
                if config.AI_FILTER_ENABLED:
                    ai_score, ai_reasoning = await ai_filter.score_vacancy(vac, {"search_query": query})
                
                # Cache for buttons
                vacancy_cache[vac_id] = vac
                
                text = hh_client.format_vacancy(vac, ai_score=ai_score if ai_score >= 0 else None, ai_reasoning=ai_reasoning)
                keyboard = build_vacancy_keyboard(vac_id)
                
                try:
                    await context.bot.send_message(
                        chat_id=target_chat_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    storage.mark_sent(vac_id) # Mark as sent now
                    shown += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Failed to send: {e}")
            if shown >= limit:
                break
        else:
            continue
    
    return shown



async def check_vacancies(context: ContextTypes.DEFAULT_TYPE, return_count: bool = False):
    """Background task to check for new vacancies."""
    global target_chat_id
    if not target_chat_id:
        logger.warning("No target chat set yet. Waiting for /start command.")
        return 0 if return_count else None

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
                # AI Filtering
                ai_score = -1
                ai_reasoning = None
                if config.AI_FILTER_ENABLED:
                    ai_score, ai_reasoning = await ai_filter.score_vacancy(vac, {"search_query": query})
                    if not ai_filter.should_send_vacancy(ai_score):
                        logger.info(f"Skipping vacancy (AI score: {ai_score}): {vac.get('name')}")
                        storage.mark_sent(vac_id)  # Mark as sent so we don't re-check
                        continue
                
                # Cache vacancy for button callbacks
                vacancy_cache[vac_id] = vac
                
                # Format message with AI score if available
                text = hh_client.format_vacancy(vac, ai_score=ai_score if ai_score >= 0 else None, ai_reasoning=ai_reasoning)
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
    
    if return_count:
        return new_count


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses."""
    query = update.callback_query
    chat_id = query.message.chat_id
    
    data = query.data
    if not data:
        await query.answer()
        return
    
    parts = data.split(":", 1)
    action = parts[0]
    value = parts[1] if len(parts) > 1 else ""
    
    # ============ Vacancy Actions ============
    if action == "fav":
        # Toggle favorite
        if storage.is_favorite(value):
            storage.remove_favorite(value)
            await query.answer("❌ Убрано из избранного")
        else:
            vacancy = vacancy_cache.get(value, {"id": value})
            storage.add_favorite(vacancy)
            await query.answer("⭐ Добавлено в избранное!")
        
        try:
            new_keyboard = build_vacancy_keyboard(value)
            await query.edit_message_reply_markup(reply_markup=new_keyboard)
        except BadRequest:
            pass
    
    elif action == "hide":
        storage.hide_vacancy(value)
        await query.answer("🙈 Вакансия скрыта")
        try:
            await query.edit_message_text(text="<i>🙈 Вакансия скрыта</i>", parse_mode="HTML")
        except BadRequest:
            pass
    
    # ============ Settings Actions ============
    elif action == "set":
        await query.answer()
        
        if value == "query":
            await query.edit_message_text(
                "🔍 Введите новый поисковый запрос.\n"
                "Можно указать несколько через запятую:\n"
                "<code>Frontend React, Vue developer, TypeScript</code>",
                parse_mode="HTML"
            )
            context.user_data["awaiting_input"] = "search_query"
        
        elif value == "salary":
            await query.edit_message_text(
                "💰 Введите минимальную зарплату (число):\n"
                "Например: <code>150000</code>\n"
                "Или <code>0</code> чтобы отключить фильтр.",
                parse_mode="HTML"
            )
            context.user_data["awaiting_input"] = "min_salary"
        
        elif value == "exp":
            keyboard = build_experience_keyboard()
            await query.edit_message_text(
                "📊 Выберите требуемый опыт:",
                reply_markup=keyboard
            )
        
        elif value == "remote":
            current = storage.get_chat_settings(chat_id)["remote_only"]
            storage.update_chat_setting(chat_id, "remote_only", not current)
            await settings(update, context) # Refresh setting menu
            
        elif value == "depth":
            current_depth = storage.get_chat_settings(chat_id).get("search_depth", 1)
            # Cycle 1->2->3->5->10->1
            depths = [1, 2, 3, 5, 10]
            try:
                idx = depths.index(current_depth)
                new_depth = depths[(idx + 1) % len(depths)]
            except ValueError:
                new_depth = 1
                
            storage.update_chat_setting(chat_id, "search_depth", new_depth)
            await settings(update, context) # Refresh setting menu
            
        elif value == "done":
             await query.message.delete()
             await query.message.reply_text("✅ Настройки сохранены. \nИспользуйте команду /jobs для поиска.")
        
        elif value == "refresh" or value == "back":
            chat_settings = storage.get_chat_settings(chat_id)
            exp_map = {
                "noExperience": "Без опыта",
                "between1And3": "1-3 года",
                "between3And6": "3-6 лет",
                "moreThan6": "6+ лет",
                "": "Любой"
            }
            msg = (
                f"⚙️ <b>Настройки бота</b>\n\n"
                f"🔍 <b>Поиск:</b> {chat_settings['search_query']}\n"
                f"💰 <b>Мин. зарплата:</b> {chat_settings['min_salary']:,} ₽\n".replace(",", " ") +
                f"📊 <b>Опыт:</b> {exp_map.get(chat_settings['experience'], chat_settings['experience'])}\n"
                f"🏠 <b>Только удаленка:</b> {'Да' if chat_settings['remote_only'] else 'Нет'}\n"
                f"🌊 <b>Глубина поиска:</b> {chat_settings.get('search_depth', 1)} стр.\n\n"
                f"Нажмите кнопку, чтобы изменить настройку:"
            )
            keyboard = build_settings_keyboard(chat_id)
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)
    
    # ============ Experience Selection ============
    elif action == "exp":
        storage.set_chat_setting(chat_id, "experience", value)
        await query.answer("✅ Опыт обновлен!")
        
        # Return to settings menu
        keyboard = build_settings_keyboard(chat_id)
        chat_settings = storage.get_chat_settings(chat_id)
        exp_map = {"noExperience": "Без опыта", "between1And3": "1-3 года", 
                   "between3And6": "3-6 лет", "moreThan6": "6+ лет", "": "Любой"}
        msg = (
            f"⚙️ <b>Настройки бота</b>\n\n"
            f"🔍 <b>Поиск:</b> {chat_settings['search_query']}\n"
            f"💰 <b>Мин. зарплата:</b> {chat_settings['min_salary']:,} ₽\n".replace(",", " ") +
            f"📊 <b>Опыт:</b> {exp_map.get(chat_settings['experience'], chat_settings['experience'])}\n"
            f"🏠 <b>Только удаленка:</b> {'Да' if chat_settings['remote_only'] else 'Нет'}\n\n"
            f"Нажмите кнопку, чтобы изменить настройку:"
        )
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=keyboard)
    
    else:
        await query.answer()


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for settings that require typing."""
    chat_id = update.effective_chat.id
    awaiting = context.user_data.get("awaiting_input")
    
    if not awaiting:
        return  # Not expecting any input
    
    text = update.message.text.strip()
    
    if awaiting == "search_query":
        storage.set_chat_setting(chat_id, "search_query", text)
        await update.message.reply_text(f"✅ Поисковый запрос обновлен:\n<b>{text}</b>", parse_mode="HTML")
    
    elif awaiting == "min_salary":
        try:
            salary = int(text.replace(" ", "").replace(",", ""))
            storage.set_chat_setting(chat_id, "min_salary", salary)
            await update.message.reply_text(f"✅ Минимальная зарплата: <b>{salary:,} ₽</b>".replace(",", " "), parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Введите число. Например: 150000")
            return  # Don't clear awaiting
    
    context.user_data["awaiting_input"] = None


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
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("stats", stats))
    
    # Button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Text input handler (for settings that require typing)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Job queue for periodic checks
    job_queue = application.job_queue
    job_queue.run_repeating(check_vacancies, interval=config.CHECK_INTERVAL_SECONDS, first=10)

    # Register command menu
    async def post_init(app):
        commands = [
            BotCommand("start", "Показать информацию"),
            BotCommand("jobs", "Проверить вакансии"),
            BotCommand("favorites", "Показать избранное"),
            BotCommand("settings", "Настройки бота"),
            BotCommand("stats", "Статистика"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands menu registered")
    
    application.post_init = post_init

    logger.info("Bot started...")
    # Allow groups - bot needs to be added with privacy mode disabled
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

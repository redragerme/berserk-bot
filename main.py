import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)
from apscheduler.schedulers.background import BackgroundScheduler

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Задать как env var на Render
DATA_FILE = "database.json"
QUOTES_FILE = "assets/quotes.txt"
IMG_RANDOM = "assets/random/"
IMG_GUTS = "assets/guts/"
IMG_GRIFFITH = "assets/griffith/"

scheduler = BackgroundScheduler()
scheduler.start()

application = ApplicationBuilder().token(BOT_TOKEN).build()
web_app = Flask(__name__)

# === ЗАГРУЗКА И СОХРАНЕНИЕ ===
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_random_quote():
    with open(QUOTES_FILE, 'r') as f:
        quotes = [line.strip() for line in f if line.strip()]
    return random.choice(quotes)

def get_random_image(folder):
    files = os.listdir(folder)
    return os.path.join(folder, random.choice(files))

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id not in data:
        data[user_id] = {
            "name": update.effective_user.first_name,
            "checkin_streak": 0,
            "last_checkin_date": None,
            "hour": None,
            "minute": None,
            "pending_change": False
        }
        save_data(data)

    await update.message.reply_text("Привет! В какое время по МСК ты хочешь получать мотивацию каждый день? Напиши в формате ЧЧ:ММ")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id in data:
        data[user_id]["hour"] = None
        data[user_id]["minute"] = None
        save_data(data)
        if scheduler.get_job(user_id):
            scheduler.remove_job(user_id)
        await update.message.reply_text("Ты больше не будешь получать напоминания. Чтобы включить снова — отправь /start")

async def show_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = data.get(user_id)
    if user and user.get("hour") is not None and user.get("minute") is not None:
        await update.message.reply_text(f"Текущее установленное время напоминания — {user['hour']:02d}:{user['minute']:02d} по МСК.")
    else:
        await update.message.reply_text("Ты ещё не установил время. Используй /start, чтобы задать его.")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛠 Доступные команды:\n"
        "/start — установить или изменить время напоминания\n"
        "/stop — остановить ежедневные напоминания\n"
        "/time — показать текущее установленное время\n"
        "/help — показать список команд"
    )
    await update.message.reply_text(text)

# === ОБРАБОТКА ВРЕМЕНИ ===
async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    data = load_data()

    try:
        hour, minute = map(int, text.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Неверный формат. Напиши в формате ЧЧ:ММ, например 09:30")
        return

    user = data.get(user_id)
    if user is None:
        return

    user["hour"] = hour
    user["minute"] = minute
    save_data(data)
    await update.message.reply_text(f"Отлично! Я буду напоминать тебе каждый день в {hour:02d}:{minute:02d} по МСК.")

# === ОБРАБОТКА КНОПОК ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()

    action, user_id = query.data.split("|")
    user = data.get(user_id)
    today = datetime.now().date().isoformat()

    if not user:
        return

    if user.get("last_checkin_date") == today:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if action == "yes":
        user["checkin_streak"] += 1
        user["last_checkin_date"] = today
        save_data(data)

        image = get_random_image(IMG_GUTS)
        with open(image, 'rb') as img:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=img,
                                         caption=f"Ты успешно отметился, так держать!\n\n🔥 Серия: {user['checkin_streak']} дней")
    elif action == "no":
        image = get_random_image(IMG_GRIFFITH)
        with open(image, 'rb') as img:
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=img,
                                         caption="Я вижу, что пока не готов противостоять тьме. Приходи когда будешь готов.")

    await query.edit_message_reply_markup(reply_markup=None)

# === ПРОВЕРКА ПРОПУЩЕННЫХ ДНЕЙ ===
async def daily_check():
    data = load_data()
    today = datetime.now().date()

    for user_id, user in data.items():
        last = user.get("last_checkin_date")
        if last and datetime.fromisoformat(last).date() < today - timedelta(days=1):
            user["checkin_streak"] = 0
            save_data(data)
            image = get_random_image(IMG_GRIFFITH)
            with open(image, 'rb') as img:
                await application.bot.send_photo(chat_id=int(user_id), photo=img,
                                                 caption="Твой путь прервался. Но ты можешь начать сначала. Отправь /start.")

scheduler.add_job(lambda: asyncio.run(daily_check()), 'cron', hour=0, minute=5)

# === WEBHOOK ===
@web_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return 'ok'

# === СТАРТ БОТА ===
if __name__ == '__main__':
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("time", show_time))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time))

    print("Бот запущен через вебхук")
    asyncio.run(application.bot.set_webhook("https://berserk-bot-tmvg.onrender.com/" + BOT_TOKEN))
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
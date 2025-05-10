import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)
from apscheduler.schedulers.background import BackgroundScheduler

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "database.json"
QUOTES_FILE = "assets/quotes.txt"
IMG_RANDOM = "assets/random/"
IMG_GUTS = "assets/guts/"
IMG_GRIFFITH = "assets/griffith/"

scheduler = BackgroundScheduler()
scheduler.start()
app = ApplicationBuilder().token(BOT_TOKEN).build()
loop = asyncio.get_event_loop()

# === ЗАГРУЗКА ДАННЫХ ===
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# === Планировщик обёртки для async-функции ===
def schedule_motivation(uid):
    return lambda: app.create_task(send_motivation(uid))

def get_random_quote():
    with open(QUOTES_FILE, 'r') as f:
        quotes = [line.strip() for line in f if line.strip()]
    return random.choice(quotes)

def get_random_image(folder):
    files = os.listdir(folder)
    return os.path.join(folder, random.choice(files))

# === КОМАНДЫ ===
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🛠 Доступные команды:\n"
        "/start — установить или изменить время напоминания\n"
        "/stop — остановить ежедневные напоминания\n"
        "/time — показать текущее установленное время\n"
        "/help — показать список команд"
    )
    await update.message.reply_text(help_text)
async def show_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    user = data.get(user_id)
    if user and user.get("hour") is not None and user.get("minute") is not None:
        await update.message.reply_text(f"Текущее установленное время напоминания — {user['hour']:02d}:{user['minute']:02d} по МСК.")
    else:
        await update.message.reply_text("Ты ещё не установил время. Используй /start, чтобы задать его.")
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
    return

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id in data:
        data[user_id]["hour"] = None
        data[user_id]["minute"] = None
        save_data(data)
        scheduler.remove_job(user_id) if scheduler.get_job(user_id) else None
        await update.message.reply_text("Ты больше не будешь получать напоминания. Чтобы включить снова — отправь /start")

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

    # если время уже установлено, спрашиваем про изменение
    if user["hour"] is not None and user["minute"] is not None and not user.get("pending_change"):
        user["temp_hour"] = hour
        user["temp_minute"] = minute
        user["pending_change"] = True
        save_data(data)

        keyboard = [[
            InlineKeyboardButton("Да", callback_data=f"change_yes|{user_id}"),
            InlineKeyboardButton("Нет", callback_data=f"change_no|{user_id}")
        ]]
        await update.message.reply_text("Ты уже установил время. Хочешь изменить его?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    data[user_id]["hour"] = hour
    data[user_id]["minute"] = minute
    data[user_id]["pending_change"] = False
    save_data(data)

    scheduler.add_job(
    lambda: asyncio.run_coroutine_threadsafe(send_motivation(user_id), loop),
    'cron',
    hour=hour,
    minute=minute,
    id=user_id,
    replace_existing=True
)
    await update.message.reply_text(f"Готово! Я буду писать тебе каждый день в {hour:02d}:{minute:02d} по МСК.")

# === МОТИВАЦИЯ ===
async def send_motivation(user_id):
    data = load_data()
    user = data.get(user_id)

    if not user:
        return

    today = datetime.now().date().isoformat()
    if user.get("last_checkin_date") == today:
        return

    quote = get_random_quote()
    image_path = get_random_image(IMG_RANDOM)

    keyboard = [[
        InlineKeyboardButton("Да", callback_data=f"yes|{user_id}"),
        InlineKeyboardButton("Нет", callback_data=f"no|{user_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    with open(image_path, 'rb') as img:
        await app.bot.send_photo(chat_id=int(user_id), photo=img, caption=f"{quote}\n\nТы готов сегодня стать на шаг ближе к лучшей версии себя?", reply_markup=reply_markup)

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

    if action == "change_yes":
        hour = user.get("temp_hour")
        minute = user.get("temp_minute")
        user["hour"] = hour
        user["minute"] = minute
        user["pending_change"] = False
        user.pop("temp_hour", None)
        user.pop("temp_minute", None)
        save_data(data)
        scheduler.add_job(
    lambda: asyncio.run_coroutine_threadsafe(send_motivation(user_id), loop),
    'cron',
    hour=hour,
    minute=minute,
    id=user_id,
    replace_existing=True
)
        await query.edit_message_text(f"Время обновлено. Я буду писать тебе каждый день в {hour:02d}:{minute:02d} по МСК.")
        return

    elif action == "change_no":
        user["pending_change"] = False
        user.pop("temp_hour", None)
        user.pop("temp_minute", None)
        save_data(data)
        await query.edit_message_text("Окей, оставим старое время без изменений.")
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
                app.bot.send_photo(chat_id=int(user_id), photo=img,
                                   caption="Твой путь прервался, но у тебя есть шанс начать все заново. Отправь команду /start.")

scheduler.add_job(lambda: app.create_task(daily_check()), 'cron', hour=0, minute=5)

# === ЗАПУСК ===
if __name__ == '__main__':
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("time", show_time))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time))
    print("Бот запущен")
    app.run_polling()
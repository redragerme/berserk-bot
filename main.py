import logging
import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = f"/{TOKEN}"
WEBHOOK_URL = f"https://berserk-bot-tmvg.onrender.com/{TOKEN}"

app = Flask(__name__)

application = Application.builder().token(TOKEN).build()

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю через вебхук на Render.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши что-нибудь, и я повторю это.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# Добавляем обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Flask endpoint для вебхука
@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.initialize())  # важно
        asyncio.run(application.process_update(update))
        return "ok", 200

# Установка вебхука
async def set_webhook():
    await application.bot.set_webhook(WEBHOOK_URL)
    print("Вебхук установлен")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(set_webhook())
    print("Бот запущен через вебхук")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
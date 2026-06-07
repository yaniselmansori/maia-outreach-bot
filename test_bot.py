import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ MESSAGE RECU: {update.message.text} de {update.effective_user.id}")
    await update.message.reply_text(f"Omar a reçu: {update.message.text}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ /start recu de {update.effective_user.id}")
    await update.message.reply_text("Omar t'entend !")

app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, echo))
print("Bot démarré — envoie un message sur Telegram")
app.run_polling()

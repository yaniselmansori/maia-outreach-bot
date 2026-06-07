import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, Response
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters,
)
import telegram_bot as bot

app = Flask(__name__)


def _build_app():
    application = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("pending", bot.pending))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(CommandHandler("export", bot.export))
    application.add_handler(CallbackQueryHandler(bot.button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    return application


@app.route("/api/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    async def _process():
        ptb_app = _build_app()
        async with ptb_app:
            update = Update.de_json(data, ptb_app.bot)
            await ptb_app.process_update(update)

    asyncio.run(_process())
    return Response("ok", status=200)

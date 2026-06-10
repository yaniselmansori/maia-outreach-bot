import asyncio
import html
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from tracker import (
    update_status, export_approved, get_stats, load_tracker, log_lead,
    get_editing_entry_id, set_editing_entry_id, reset_pending,
)
from claude_client import generate_message, parse_outreach_command
from apollo_client import search_people
from clay_client import enrich_with_clay

logging.basicConfig(level=logging.INFO)

YOUR_TELEGRAM_ID = int(os.environ["TELEGRAM_USER_ID"])

e = html.escape  # shorthand for escaping user content in HTML messages


def is_authorized(update: Update) -> bool:
    return update.effective_user.id == YOUR_TELEGRAM_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "👋 <b>Omar Lahlou — Agent Outreach MAIA</b>\n\n"
        "Parle-moi naturellement :\n"
        '› <i>"Trouve 5 CEO de PME dans la construction"</i>\n'
        '› <i>"10 DG logistique à Lyon"</i>\n'
        '› <i>"3 DAF dans le retail"</i>\n\n'
        "Commandes :\n"
        "/pending — valider les messages\n"
        "/stats — tableau de bord\n"
        "/export — afficher les messages approuvés à envoyer\n"
        "/reset — vider la file en attente",
        parse_mode="HTML",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    text = update.message.text.strip()

    # State: waiting for edited message
    entry_id = get_editing_entry_id()
    if entry_id:
        update_status(entry_id, "approved", final_message=text)
        await update.message.reply_text(f"✅ Message #{entry_id} modifié et approuvé.")
        await _send_next_pending(update, context)
        return

    # Default: natural language outreach command
    await update.message.reply_text("⏳ Je cherche les profils sur Apollo...")

    try:
        criteria = parse_outreach_command(text)

        await update.message.reply_text(
            f"🎯 <b>Critères détectés :</b>\n"
            f"Secteur : {e(criteria.get('sector', '—'))}\n"
            f"Titres : {e(', '.join(criteria.get('titles', [])))}\n"
            f"Taille : {criteria.get('company_size_min')}–{criteria.get('company_size_max')} sal.\n"
            f"Géo : {e(criteria.get('location', 'France'))}\n"
            f"Nombre : {criteria.get('count', 10)}\n\n"
            "🔍 Recherche Apollo en cours...",
            parse_mode="HTML",
        )

        leads = search_people(criteria)

        if not leads:
            await update.message.reply_text("❌ Aucun profil trouvé. Essaie d'élargir les critères.")
            return

        await update.message.reply_text(
            f"✅ <b>{len(leads)} profils trouvés.</b> Génération des messages en cours...",
            parse_mode="HTML",
        )

        loop = asyncio.get_running_loop()

        async def process_one(lead):
            lead = await loop.run_in_executor(None, enrich_with_clay, lead)
            message, version = await loop.run_in_executor(None, generate_message, lead)
            log_lead(lead, message, version, status="pending")

        await asyncio.gather(*[process_one(lead) for lead in leads])

        await update.message.reply_text(
            f"🎉 <b>{len(leads)} messages générés !</b>\n\nTape /pending pour les valider.",
            parse_mode="HTML",
        )

    except Exception as exc:
        logging.exception("Erreur dans handle_text")
        await update.message.reply_text(f"❌ Erreur : {str(exc)}")


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = load_tracker()
    queue = [entry for entry in data if entry["status"] == "pending"]
    if not queue:
        await update.message.reply_text("✅ Aucun message en attente.")
        return
    await update.message.reply_text(
        f"📋 <b>{len(queue)} message(s) en attente</b>", parse_mode="HTML"
    )
    await _send_validation_card(update.message, queue[0])


async def _send_validation_card(target, entry: dict):
    version_emoji = "🔵" if entry["version"] == "B" else "⚪"
    text = (
        f"{version_emoji} <b>Version {entry['version']}</b> — Lead #{entry['id']}\n"
        f"👤 <b>{e(entry['first_name'])} {e(entry.get('last_name', ''))}</b>"
        f" — {e(entry['company'])} ({e(entry['sector'])})\n"
        f"💼 {e(entry.get('title', ''))}\n\n"
        f"📝 <b>Message :</b>\n<i>{e(entry['message'])}</i>"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approuver", callback_data=f"approve:{entry['id']}"),
            InlineKeyboardButton("❌ Rejeter", callback_data=f"reject:{entry['id']}"),
        ],
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit:{entry['id']}")],
    ])
    await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    query = update.callback_query
    await query.answer()

    action, entry_id = query.data.split(":")
    entry_id = int(entry_id)

    if action == "approve":
        update_status(entry_id, "approved")
        await query.edit_message_text(f"✅ Message #{entry_id} approuvé.")
        await _send_next_pending(update, context)

    elif action == "reject":
        update_status(entry_id, "rejected")
        await query.edit_message_text(f"❌ Message #{entry_id} rejeté.")
        await _send_next_pending(update, context)

    elif action == "edit":
        set_editing_entry_id(entry_id)
        data = load_tracker()
        entry = next(ent for ent in data if ent["id"] == entry_id)
        await query.edit_message_text(
            f"✏️ <b>Modifier le message #{entry_id}</b>\n\n"
            f"Message actuel :\n<i>{e(entry['message'])}</i>\n\n"
            "Envoie le nouveau message :",
            parse_mode="HTML",
        )


async def _send_next_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_tracker()
    queue = [entry for entry in data if entry["status"] == "pending"]
    target = update.message or update.callback_query.message
    if queue:
        await _send_validation_card(target, queue[0])
    else:
        await target.reply_text("🎉 Tous validés ! Tape /export pour afficher les messages à envoyer.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    s = get_stats()
    await update.message.reply_text(
        f"📊 <b>Stats Outreach MAIA</b>\n\n"
        f"Total : {s['total']}\n"
        f"⏳ En attente : {s['pending']}\n"
        f"✅ Approuvés : {s['approved']}\n"
        f"❌ Rejetés : {s['rejected']}\n"
        f"📤 Envoyés : {s['sent']}",
        parse_mode="HTML",
    )


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = load_tracker()
    approved = [entry for entry in data if entry["status"] == "approved"]
    if not approved:
        await update.message.reply_text("Aucun message approuvé.")
        return
    await update.message.reply_text(
        f"📤 <b>{len(approved)} message(s) à envoyer :</b>", parse_mode="HTML"
    )
    for entry in approved:
        text = (
            f"👤 <b>{e(entry['first_name'])} {e(entry.get('last_name', ''))}</b>"
            f" — {e(entry['company'])}\n"
            f"🔗 {entry.get('linkedin_url', 'LinkedIn non disponible')}\n\n"
            f"{e(entry['message'])}"
        )
        await update.message.reply_text(text, parse_mode="HTML")
        update_status(entry["id"], "sent")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    count = reset_pending()
    await update.message.reply_text(f"🗑️ {count} message(s) en attente supprimés.")


def run():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    run()

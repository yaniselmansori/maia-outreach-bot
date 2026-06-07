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
from tracker import update_status, export_approved, get_stats, load_tracker, log_lead
from claude_client import generate_message, parse_outreach_command
from apollo_client import search_people
from clay_client import enrich_with_clay

logging.basicConfig(level=logging.INFO)

YOUR_TELEGRAM_ID = int(os.environ["TELEGRAM_USER_ID"])


def is_authorized(update: Update) -> bool:
    return update.effective_user.id == YOUR_TELEGRAM_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    context.user_data.clear()
    await update.message.reply_text(
        "👋 *Omar Lahlou — Agent Outreach MAIA*\n\n"
        "Parle-moi naturellement :\n"
        "› _\"Trouve 5 CEO de PME dans la construction\"_\n"
        "› _\"10 DG logistique à Lyon\"_\n"
        "› _\"3 DAF dans le retail\"_\n\n"
        "Commandes :\n"
        "/pending — valider les messages\n"
        "/stats — tableau de bord\n"
        "/export — afficher les messages approuvés à envoyer",
        parse_mode="Markdown",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    text = update.message.text.strip()

    # State: waiting for edited message
    if context.user_data.get("awaiting_edit"):
        entry_id = context.user_data.pop("awaiting_edit")
        update_status(entry_id, "approved", final_message=text)
        await update.message.reply_text(f"✅ Message #{entry_id} modifié et approuvé.")
        await _send_next_pending(update, context)
        return

    # Default: natural language outreach command
    await update.message.reply_text("⏳ Je cherche les profils sur Apollo...")

    try:
        criteria = parse_outreach_command(text)

        await update.message.reply_text(
            f"🎯 *Critères détectés :*\n"
            f"Secteur : {criteria.get('sector', '—')}\n"
            f"Titres : {', '.join(criteria.get('titles', []))}\n"
            f"Taille : {criteria.get('company_size_min')}–{criteria.get('company_size_max')} sal.\n"
            f"Géo : {criteria.get('location', 'France')}\n"
            f"Nombre : {criteria.get('count', 10)}\n\n"
            "🔍 Recherche Apollo en cours...",
            parse_mode="Markdown",
        )

        leads = search_people(criteria)

        if not leads:
            await update.message.reply_text("❌ Aucun profil trouvé. Essaie d'élargir les critères.")
            return

        await update.message.reply_text(
            f"✅ *{len(leads)} profils trouvés.* Enrichissement Clay en cours...",
            parse_mode="Markdown",
        )

        for lead in leads:
            lead = enrich_with_clay(lead)
            message, version = generate_message(lead)
            log_lead(lead, message, version, status="pending")

        await update.message.reply_text(
            f"🎉 *{len(leads)} messages générés !*\n\nTape /pending pour les valider.",
            parse_mode="Markdown",
        )

    except Exception as e:
        logging.exception("Erreur dans handle_text")
        await update.message.reply_text(f"❌ Erreur : {str(e)}")


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = load_tracker()
    queue = [e for e in data if e["status"] == "pending"]
    if not queue:
        await update.message.reply_text("✅ Aucun message en attente.")
        return
    await update.message.reply_text(f"📋 *{len(queue)} message(s) en attente*", parse_mode="Markdown")
    await _send_validation_card(update.message, queue[0])


async def _send_validation_card(target, entry: dict):
    version_emoji = "🔵" if entry["version"] == "B" else "⚪"
    text = (
        f"{version_emoji} *Version {entry['version']}* — Lead #{entry['id']}\n"
        f"👤 *{entry['first_name']} {entry.get('last_name', '')}* — {entry['company']} ({entry['sector']})\n"
        f"💼 {entry.get('title', '')}\n\n"
        f"📝 *Message :*\n_{entry['message']}_"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approuver", callback_data=f"approve:{entry['id']}"),
            InlineKeyboardButton("❌ Rejeter", callback_data=f"reject:{entry['id']}"),
        ],
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit:{entry['id']}")],
    ])
    await target.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


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
        context.user_data["awaiting_edit"] = entry_id
        data = load_tracker()
        entry = next(e for e in data if e["id"] == entry_id)
        await query.edit_message_text(
            f"✏️ *Modifier le message #{entry_id}*\n\n"
            f"Message actuel :\n_{entry['message']}_\n\n"
            "Envoie le nouveau message :",
            parse_mode="Markdown",
        )


async def _send_next_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_tracker()
    queue = [e for e in data if e["status"] == "pending"]
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
        f"📊 *Stats Outreach MAIA*\n\n"
        f"Total : {s['total']}\n"
        f"⏳ En attente : {s['pending']}\n"
        f"✅ Approuvés : {s['approved']}\n"
        f"❌ Rejetés : {s['rejected']}\n"
        f"📤 Envoyés : {s['sent']}",
        parse_mode="Markdown",
    )


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = load_tracker()
    approved = [e for e in data if e["status"] == "approved"]
    if not approved:
        await update.message.reply_text("Aucun message approuvé.")
        return
    await update.message.reply_text(f"📤 *{len(approved)} message(s) à envoyer :*", parse_mode="Markdown")
    for entry in approved:
        text = (
            f"👤 *{entry['first_name']} {entry.get('last_name', '')}* — {entry['company']}\n"
            f"🔗 {entry.get('linkedin_url', 'LinkedIn non disponible')}\n\n"
            f"{entry['message']}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
        update_status(entry["id"], "sent")


def run():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()


if __name__ == "__main__":
    run()

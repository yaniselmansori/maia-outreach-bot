"""
MAIA Outreach Bot
Flow: commande naturelle → Apollo → Claude (LinkedIn + script appel) → validation Telegram
"""
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
from claude_client import generate_outreach, parse_outreach_command
from pappers_client import search_people

logging.basicConfig(level=logging.INFO)

YOUR_TELEGRAM_ID = int(os.environ["TELEGRAM_USER_ID"])

e = html.escape


def is_authorized(update: Update) -> bool:
    return update.effective_user.id == YOUR_TELEGRAM_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "👋 <b>MAIA — Agent Outreach</b>\n\n"
        "Parle-moi naturellement :\n"
        '› <i>"Trouve 5 CEO de PME dans la construction"</i>\n'
        '› <i>"10 DG logistique à Lyon"</i>\n'
        '› <i>"3 DAF dans le retail"</i>\n\n'
        "Commandes :\n"
        "/pending — valider les leads\n"
        "/stats — tableau de bord\n"
        "/export — exporter les approuvés\n"
        "/reset — vider la file en attente",
        parse_mode="HTML",
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    text = update.message.text.strip()

    # State: waiting for edited LinkedIn message
    entry_id = get_editing_entry_id()
    if entry_id:
        update_status(entry_id, "approved", channel="linkedin", final_message=text)
        await update.message.reply_text(f"✅ Message #{entry_id} modifié et approuvé (LinkedIn).")
        await _send_next_pending(update, context)
        return

    await update.message.reply_text("⏳ Recherche Apollo en cours...")

    try:
        criteria = parse_outreach_command(text)

        await update.message.reply_text(
            f"🎯 <b>Critères détectés :</b>\n"
            f"Secteur : {e(criteria.get('sector', '—'))}\n"
            f"Titres : {e(', '.join(criteria.get('titles', [])))}\n"
            f"Taille : {criteria.get('company_size_min')}–{criteria.get('company_size_max')} sal.\n"
            f"Géo : {e(criteria.get('location', 'France'))}\n"
            f"Nombre : {criteria.get('count', 10)}\n\n"
            "🔍 Recherche en cours...",
            parse_mode="HTML",
        )

        existing = load_tracker()
        seen_ids = set()
        for ent in existing:
            if ent.get("siren"):
                seen_ids.add(f"pappers:{ent['siren']}")
            elif ent.get("linkedin_url"):
                seen_ids.add(ent["linkedin_url"])
        leads = search_people(criteria, exclude_urls=seen_ids)

        if not leads:
            await update.message.reply_text("❌ Aucun profil trouvé. Essaie d'élargir les critères.")
            return

        await update.message.reply_text(
            f"✅ <b>{len(leads)} profils trouvés.</b> Génération des messages...",
            parse_mode="HTML",
        )

        loop = asyncio.get_running_loop()

        async def process_one(lead):
            linkedin_msg, call_script = await loop.run_in_executor(None, generate_outreach, lead)
            log_lead(lead, linkedin_msg, call_script, status="pending")

        await asyncio.gather(*[process_one(lead) for lead in leads])

        await update.message.reply_text(
            f"🎉 <b>{len(leads)} leads prêts !</b>\n\nTape /pending pour les valider.",
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
        await update.message.reply_text("✅ Aucun lead en attente.")
        return
    await update.message.reply_text(
        f"📋 <b>{len(queue)} lead(s) en attente</b>", parse_mode="HTML"
    )
    await _send_validation_card(update.message, queue[0])


async def _send_validation_card(target, entry: dict):
    linkedin = entry.get("linkedin_url", "")
    phone = entry.get("phone", "")
    city = entry.get("city", "")
    linkedin_line = f'\n🔗 <a href="{linkedin}">LinkedIn</a>' if linkedin else ""
    phone_line = f"\n📞 {e(phone)}" if phone else "\n📞 Numéro non disponible"
    city_line = f" · {e(city)}" if city else ""

    linkedin_msg = entry.get("linkedin_msg") or entry.get("message", "")
    call_script = entry.get("call_script", "")

    call_block = f"\n\n📞 <b>Script appel :</b>\n<i>{e(call_script)}</i>" if call_script else ""

    text = (
        f"<b>Lead #{entry['id']}</b>\n"
        f"👤 <b>{e(entry['first_name'])} {e(entry.get('last_name', ''))}</b>"
        f" — {e(entry['company'])}{city_line}\n"
        f"💼 {e(entry.get('title', ''))}"
        f"{linkedin_line}"
        f"{phone_line}\n\n"
        f"💬 <b>LinkedIn :</b>\n<i>{e(linkedin_msg)}</i>"
        f"{call_block}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📞 Appeler", callback_data=f"call:{entry['id']}"),
            InlineKeyboardButton("💼 LinkedIn", callback_data=f"linkedin:{entry['id']}"),
        ],
        [
            InlineKeyboardButton("✏️ Modifier message", callback_data=f"edit:{entry['id']}"),
            InlineKeyboardButton("❌ Passer", callback_data=f"reject:{entry['id']}"),
        ],
    ])
    await target.reply_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    query = update.callback_query
    await query.answer()

    action, entry_id = query.data.split(":")
    entry_id = int(entry_id)

    if action == "call":
        update_status(entry_id, "approved", channel="call")
        data = load_tracker()
        entry = next(ent for ent in data if ent["id"] == entry_id)
        phone = entry.get("phone", "")
        call_script = entry.get("call_script", "")
        phone_line = f"\n📞 <b>{e(phone)}</b>" if phone else "\n📞 Numéro non disponible"
        await query.edit_message_text(
            f"📞 <b>{e(entry['first_name'])} {e(entry.get('last_name',''))} — {e(entry['company'])}</b>"
            f"{phone_line}\n\n"
            f"<i>{e(call_script)}</i>",
            parse_mode="HTML",
        )
        await _send_next_pending(update, context)

    elif action == "linkedin":
        update_status(entry_id, "approved", channel="linkedin")
        await query.edit_message_text(f"💼 Lead #{entry_id} — LinkedIn approuvé.")
        await _send_next_pending(update, context)

    elif action == "reject":
        update_status(entry_id, "rejected")
        await query.edit_message_text(f"❌ Lead #{entry_id} passé.")
        await _send_next_pending(update, context)

    elif action == "edit":
        set_editing_entry_id(entry_id)
        data = load_tracker()
        entry = next(ent for ent in data if ent["id"] == entry_id)
        await query.edit_message_text(
            f"✏️ <b>Modifier le message LinkedIn #{entry_id}</b>\n\n"
            f"Message actuel :\n<i>{e(entry.get('linkedin_msg', ''))}</i>\n\n"
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
        await target.reply_text("🎉 Tous traités ! Tape /export pour exporter.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    s = get_stats()
    data = load_tracker()
    calls = sum(1 for e in data if e.get("channel") == "call" and e["status"] == "approved")
    linkedins = sum(1 for e in data if e.get("channel") == "linkedin" and e["status"] == "approved")
    await update.message.reply_text(
        f"📊 <b>Stats Outreach MAIA</b>\n\n"
        f"Total : {s['total']}\n"
        f"⏳ En attente : {s['pending']}\n"
        f"✅ Approuvés : {s['approved']} (📞 {calls} appels / 💼 {linkedins} LinkedIn)\n"
        f"❌ Passés : {s['rejected']}\n"
        f"📤 Traités : {s['sent']}",
        parse_mode="HTML",
    )


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    data = load_tracker()
    approved = [entry for entry in data if entry["status"] == "approved"]
    if not approved:
        await update.message.reply_text("Aucun lead approuvé.")
        return

    calls = [e for e in approved if e.get("channel") == "call"]
    linkedins = [e for e in approved if e.get("channel") == "linkedin"]

    if calls:
        await update.message.reply_text(f"📞 <b>{len(calls)} appel(s) à passer :</b>", parse_mode="HTML")
        for entry in calls:
            text = (
                f"👤 <b>{e(entry['first_name'])} {e(entry.get('last_name', ''))}</b> — {e(entry['company'])}\n"
                f"📞 {e(entry.get('phone', 'Non disponible'))}\n\n"
                f"<i>{e(entry.get('call_script', ''))}</i>"
            )
            await update.message.reply_text(text, parse_mode="HTML")
            update_status(entry["id"], "sent")

    if linkedins:
        await update.message.reply_text(f"💼 <b>{len(linkedins)} message(s) LinkedIn :</b>", parse_mode="HTML")
        for entry in linkedins:
            text = (
                f"👤 <b>{e(entry['first_name'])} {e(entry.get('last_name', ''))}</b> — {e(entry['company'])}\n"
                f"🔗 {entry.get('linkedin_url', 'Non disponible')}\n\n"
                f"{e(entry.get('linkedin_msg', ''))}"
            )
            await update.message.reply_text(text, parse_mode="HTML")
            update_status(entry["id"], "sent")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    count = reset_pending()
    await update.message.reply_text(f"🗑️ {count} lead(s) en attente supprimés.")


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

"""
MAIA Outreach Agent
Flow: Apollo CSV → Clay enrichment → Claude message → Telegram validation → Waalaxy export
"""
import csv
import sys
from claude_client import generate_message
from tracker import log_lead
from clay_client import enrich_with_clay


def process_leads_from_csv(filepath: str):
    """
    Read leads from Apollo CSV export, enrich via Clay, generate messages.
    Logs all to tracker with status=pending for Telegram validation.
    """
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"📋 {len(leads)} leads chargés depuis {filepath}")

    for i, raw_lead in enumerate(leads, 1):
        lead = {
            "first_name": raw_lead.get("First Name", raw_lead.get("first_name", "")),
            "last_name": raw_lead.get("Last Name", raw_lead.get("last_name", "")),
            "company": raw_lead.get("Company", raw_lead.get("company", "")),
            "title": raw_lead.get("Title", raw_lead.get("title", "")),
            "sector": raw_lead.get("Industry", raw_lead.get("sector", "")),
            "company_size": raw_lead.get("# Employees", raw_lead.get("company_size", "")),
            "linkedin_url": raw_lead.get("LinkedIn Url", raw_lead.get("linkedin_url", "")),
            "ai_signal": "",
        }

        print(f"[{i}/{len(leads)}] Traitement : {lead['first_name']} {lead['last_name']} — {lead['company']}")

        # Enrich with Clay
        lead = enrich_with_clay(lead)

        # Generate message with Claude
        message, version = generate_message(lead)

        # Log to tracker (status=pending → waits for Telegram validation)
        log_lead(lead, message, version, status="pending")

        print(f"  → Version {version} générée ({'signal IA détecté' if version == 'B' else 'profil froid'})")

    print(f"\n✅ {len(leads)} messages générés et en attente de validation sur Telegram.")
    print("Lance le bot Telegram pour valider : python telegram_bot.py")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py leads.csv")
        sys.exit(1)

    process_leads_from_csv(sys.argv[1])

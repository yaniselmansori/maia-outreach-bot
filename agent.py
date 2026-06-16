"""
MAIA Outreach Agent
Flow: Apollo CSV → Claude (LinkedIn + script appel) → Telegram validation
"""
import csv
import sys
from claude_client import generate_outreach
from tracker import log_lead


def process_leads_from_csv(filepath: str):
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
            "phone": raw_lead.get("Phone", raw_lead.get("phone", "")),
        }

        print(f"[{i}/{len(leads)}] {lead['first_name']} {lead['last_name']} — {lead['company']}")

        linkedin_msg, call_script = generate_outreach(lead)
        log_lead(lead, linkedin_msg, call_script, status="pending")

        print(f"  → Messages générés")

    print(f"\n✅ {len(leads)} leads en attente de validation sur Telegram.")
    print("Lance le bot Telegram pour valider : python telegram_bot.py")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py leads.csv")
        sys.exit(1)

    process_leads_from_csv(sys.argv[1])

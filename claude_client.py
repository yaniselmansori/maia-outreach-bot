import anthropic
import os
import json
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROMPTS_DIR = Path(__file__).parent / "prompts"


def generate_outreach(lead: dict) -> tuple[str, str]:
    """
    Generate LinkedIn message + call script for a lead.
    Returns (linkedin_message, call_script).
    """
    template = (PROMPTS_DIR / "outreach.txt").read_text()
    prompt = template.format(
        first_name=lead.get("first_name", ""),
        company=lead.get("company", ""),
        sector=lead.get("sector", ""),
        company_size=lead.get("company_size", ""),
        title=lead.get("title", ""),
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("linkedin", ""), data.get("call_script", "")
        except json.JSONDecodeError:
            logging.warning(f"JSON invalide: {match.group()}")

    return raw, ""


def parse_outreach_command(text: str) -> dict:
    """
    Parse a natural language outreach command into Apollo search criteria.
    """
    prompt = f"""Extrait les critères de recherche depuis cette commande.

Commande : "{text}"

Retourne UNIQUEMENT ce JSON, sans aucun texte avant ou après :
{{"sector": "construction", "titles": ["CEO", "Directeur Général", "DG", "Gérant"], "count": 3, "company_size_min": 20, "company_size_max": 200, "location": "France"}}

Adapte les valeurs à la commande. Titres selon le rôle :
- CEO/DG/patron/gérant → ["CEO", "Directeur Général", "DG", "Gérant", "PDG"]
- DAF/CFO/financier → ["DAF", "CFO", "Directeur Financier", "Directeur Administratif et Financier"]
- COO/opérations → ["COO", "Directeur des Opérations"]
- Commercial/sales → ["Directeur Commercial", "Sales Director"]"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    logging.info(f"Claude Haiku raw response: {repr(raw)}")

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            logging.warning(f"JSON invalide dans: {match.group()}")

    logging.warning("Fallback: parsing manuel de la commande")
    return _fallback_parse(text)


def _fallback_parse(text: str) -> dict:
    text_lower = text.lower()

    count_match = re.search(r'\b(\d+)\b', text)
    count = int(count_match.group(1)) if count_match else 10

    sector_map = {
        "construction": "construction",
        "logistique": "logistique",
        "transport": "transport",
        "retail": "retail",
        "distribution": "distribution",
        "industrie": "industrie",
        "restauration": "restauration",
        "immobilier": "immobilier",
    }
    sector = next((v for k, v in sector_map.items() if k in text_lower), "")

    if any(w in text_lower for w in ["ceo", "dg", "directeur général", "gérant", "patron", "pdg"]):
        titles = ["CEO", "Directeur Général", "DG", "Gérant", "PDG"]
    elif any(w in text_lower for w in ["daf", "cfo", "financier"]):
        titles = ["DAF", "CFO", "Directeur Financier"]
    elif any(w in text_lower for w in ["coo", "opérations"]):
        titles = ["COO", "Directeur des Opérations"]
    elif any(w in text_lower for w in ["commercial", "sales"]):
        titles = ["Directeur Commercial", "Sales Director"]
    else:
        titles = ["CEO", "Directeur Général", "DG", "Gérant"]

    return {
        "sector": sector,
        "titles": titles,
        "count": count,
        "company_size_min": 20,
        "company_size_max": 200,
        "location": "France",
    }

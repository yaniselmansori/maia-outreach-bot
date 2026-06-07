import anthropic
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROMPTS_DIR = Path(__file__).parent / "prompts"


def generate_message(lead: dict) -> tuple[str, str]:
    """
    Generate a personalized outreach message for a lead.
    Returns (message, version) where version is "A" or "B".
    """
    has_signal = bool(lead.get("ai_signal", "").strip())
    version = "B" if has_signal else "A"

    template_file = PROMPTS_DIR / f"version_{'b' if has_signal else 'a'}.txt"
    template = template_file.read_text()

    prompt = template.format(
        first_name=lead.get("first_name", ""),
        company=lead.get("company", ""),
        sector=lead.get("sector", ""),
        company_size=lead.get("company_size", ""),
        title=lead.get("title", ""),
        ai_signal=lead.get("ai_signal", ""),
    )

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip(), version


def parse_outreach_command(text: str) -> dict:
    """
    Parse a natural language outreach command into Apollo search criteria.
    Uses Haiku for speed and cost efficiency.
    """
    import json
    import re

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
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    raw = response.content[0].text.strip()
    logging.info(f"Claude Haiku raw response: {repr(raw)}")

    # Extract JSON block even if Claude adds surrounding text
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            logging.warning(f"JSON invalide dans: {match.group()}")

    # Fallback: extract keywords manually from the original text
    logging.warning("Fallback: parsing manuel de la commande")
    return _fallback_parse(text)


def _fallback_parse(text: str) -> dict:
    """Manual keyword extraction when Claude JSON fails."""
    text_lower = text.lower()

    # Detect count
    import re
    count_match = re.search(r'\b(\d+)\b', text)
    count = int(count_match.group(1)) if count_match else 10

    # Detect sector
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

    # Detect titles
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

import os
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def enrich_with_clay(lead: dict) -> dict:
    prompt = f"""Tu es un expert en prospection B2B PME France/Maroc.

Analyse ce prospect et génère un signal d'accroche UNIQUEMENT si tu peux produire quelque chose de spécifique et crédible — un fait sectoriel précis, une tension opérationnelle réelle propre à ce type d'entreprise, ou un contexte marché actuel vérifiable.

Si tu ne peux produire qu'une phrase générique qui s'appliquerait à n'importe quelle entreprise du secteur, réponds exactement : AUCUN_SIGNAL

Prospect :
- Prénom : {lead.get('first_name', '')}
- Titre : {lead.get('title', '')}
- Entreprise : {lead.get('company', '')}
- Secteur : {lead.get('sector', '')}
- Taille : {lead.get('company_size', '')} salariés

Retourne UNIQUEMENT la phrase d'accroche ou AUCUN_SIGNAL, rien d'autre."""

    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    signal = response.content[0].text.strip()
    lead["ai_signal"] = "" if signal == "AUCUN_SIGNAL" else signal
    return lead

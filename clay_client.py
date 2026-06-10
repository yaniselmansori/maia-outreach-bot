import os
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def enrich_with_clay(lead: dict) -> dict:
    prompt = f"""Tu es un expert en prospection B2B PME France/Maroc.

Génère un signal d'accroche court (1 phrase max) pour ce prospect, basé sur son contexte métier.
Le signal doit justifier naturellement pourquoi on le contacte maintenant — sans mentir, sans inventer.
Utilise uniquement les données fournies.

Prospect :
- Prénom : {lead.get('first_name', '')}
- Titre : {lead.get('title', '')}
- Entreprise : {lead.get('company', '')}
- Secteur : {sector}
- Taille : {company_size} salariés

Retourne UNIQUEMENT la phrase d'accroche, rien d'autre."""

    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )

    lead["ai_signal"] = response.content[0].text.strip()
    return lead

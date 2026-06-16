import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PAPPERS_API_KEY = os.environ.get("PAPPERS_API_KEY")
BASE_URL = "https://api.pappers.fr/v2"

# NAF division codes by sector (2-digit prefix)
SECTOR_NAF_PREFIXES = {
    "construction": ["41", "42", "43"],
    "logistique": ["52"],
    "transport": ["49"],
    "retail": ["47"],
    "distribution": ["46"],
    "industrie": ["24", "25", "26", "27", "28", "29", "30"],
    "restauration": ["56"],
    "immobilier": ["68"],
    "agroalimentaire": ["10", "11"],
    "hôtellerie": ["55"],
}

# Pappers tranche_effectif codes
# 12=20-49, 21=50-99, 22=100-199, 31=200-249
TRANCHE_MIN = {20: "12", 50: "21", 100: "22", 200: "31"}
TRANCHE_MAX = {49: "12", 99: "21", 199: "22", 249: "31"}

DIRECTOR_KEYWORDS = [
    "président", "gérant", "directeur général", "pdg", "dg",
    "associé gérant", "président directeur", "directeur",
]


def _is_director(qualite: str) -> bool:
    if not qualite:
        return False
    q = qualite.lower()
    return any(kw in q for kw in DIRECTOR_KEYWORDS)


def _tranche_min(size_min: int) -> str:
    for threshold, code in sorted(TRANCHE_MIN.items()):
        if size_min <= threshold:
            return code
    return "31"


def _tranche_max(size_max: int) -> str:
    for threshold, code in sorted(TRANCHE_MAX.items()):
        if size_max <= threshold:
            return code
    return "31"


def search_people(criteria: dict, exclude_urls: set = None) -> list[dict]:
    """
    Search French company directors via Pappers (RCS/INPI registry).
    Returns leads with company phone numbers.
    exclude_urls contains siren-based IDs like 'pappers:123456789'.
    """
    sector = criteria.get("sector", "").lower()
    target_count = criteria.get("count", 5)
    size_min = criteria.get("company_size_min", 20)
    size_max = criteria.get("company_size_max", 200)
    exclude_urls = exclude_urls or set()

    naf_prefixes = SECTOR_NAF_PREFIXES.get(sector, [])

    leads = []
    page = 1

    while len(leads) < target_count and page <= 15:
        params = {
            "api_token": PAPPERS_API_KEY,
            "per_page": 25,
            "page": page,
            "tranche_effectif_min": _tranche_min(size_min),
            "tranche_effectif_max": _tranche_max(size_max),
        }

        # Add NAF filter if sector known
        if naf_prefixes:
            params["code_naf"] = naf_prefixes[0]  # primary sector code

        response = requests.get(
            f"{BASE_URL}/recherche",
            params=params,
            timeout=30,
        )

        if response.status_code != 200:
            raise Exception(f"Pappers error {response.status_code}: {response.text}")

        companies = response.json().get("resultats", [])
        if not companies:
            break

        for company in companies:
            if len(leads) >= target_count:
                break

            siren = company.get("siren", "")
            unique_id = f"pappers:{siren}"
            if unique_id in exclude_urls:
                continue

            representants = company.get("representants", [])
            directors = [
                r for r in representants
                if r.get("type") == "personne_physique" and _is_director(r.get("qualite", ""))
            ]
            if not directors:
                continue

            director = directors[0]
            siege = company.get("siege", {})
            phone = siege.get("telephone", "")

            effectif = company.get("effectif", "")
            if not effectif:
                e_min = company.get("effectif_min", "")
                e_max = company.get("effectif_max", "")
                effectif = f"{e_min}-{e_max}" if e_min else ""

            leads.append({
                "first_name": director.get("prenom", "").title(),
                "last_name": director.get("nom", "").title(),
                "company": company.get("nom_entreprise", ""),
                "title": director.get("qualite", ""),
                "sector": sector,
                "company_size": str(effectif),
                "linkedin_url": "",
                "phone": phone,
                "siren": siren,
                "city": siege.get("ville", ""),
            })

        page += 1

    return leads

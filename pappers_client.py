import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PAPPERS_API_KEY = os.environ.get("PAPPERS_API_KEY")
BASE_URL = "https://api.pappers.fr/v2"

SECTOR_NAF = {
    "construction": "41.20B",
    "logistique": "52.10B",
    "transport": "49.41A",
    "retail": "47.11F",
    "distribution": "46.90Z",
    "industrie": "25.11Z",
    "restauration": "56.10A",
    "immobilier": "68.20A",
    "agroalimentaire": "10.89Z",
    "hôtellerie": "55.10Z",
}

DIRECTOR_KEYWORDS = [
    "président", "gérant", "directeur général", "pdg", "dg",
    "associé gérant", "chef d'entreprise", "directeur",
]

# Pappers tranche_effectif codes: 12=20-49, 21=50-99, 22=100-199, 31=200-249
def _tranche(size: int, mode: str) -> str:
    if mode == "min":
        if size >= 200: return "31"
        if size >= 100: return "22"
        if size >= 50:  return "21"
        return "12"
    else:
        if size >= 200: return "31"
        if size >= 100: return "22"
        if size >= 50:  return "21"
        return "12"


def _is_director(qualite: str) -> bool:
    if not qualite:
        return False
    q = qualite.lower()
    return any(kw in q for kw in DIRECTOR_KEYWORDS)


def _get_company_detail(siren: str) -> dict:
    r = requests.get(
        f"{BASE_URL}/entreprise",
        params={"api_token": PAPPERS_API_KEY, "siren": siren},
        timeout=15,
    )
    if r.status_code != 200:
        return {}
    return r.json()


def search_people(criteria: dict, exclude_urls: set = None) -> list[dict]:
    """
    Two-pass Pappers search:
    1. Search companies by sector/size → get SIRENs
    2. Fetch company detail per SIREN → get real dirigeants names + phone
    """
    sector = criteria.get("sector", "").lower()
    target_count = criteria.get("count", 5)
    size_min = criteria.get("company_size_min", 20)
    size_max = criteria.get("company_size_max", 200)
    exclude_urls = exclude_urls or set()

    naf = SECTOR_NAF.get(sector, "")

    leads = []
    page = 1

    while len(leads) < target_count and page <= 20:
        params = {
            "api_token": PAPPERS_API_KEY,
            "per_page": 20,
            "page": page,
            "tranche_effectif_min": _tranche(size_min, "min"),
            "tranche_effectif_max": _tranche(size_max, "max"),
        }
        if naf:
            params["code_naf"] = naf

        r = requests.get(f"{BASE_URL}/recherche", params=params, timeout=30)
        if r.status_code != 200:
            raise Exception(f"Pappers search error {r.status_code}: {r.text}")

        companies = r.json().get("resultats", [])
        if not companies:
            break

        for company in companies:
            if len(leads) >= target_count:
                break

            siren = company.get("siren", "")
            if not siren:
                continue

            unique_id = f"pappers:{siren}"
            if unique_id in exclude_urls:
                continue

            # Fetch full detail to get dirigeants
            detail = _get_company_detail(siren)
            if not detail:
                continue

            representants = detail.get("representants", [])
            directors = [
                rep for rep in representants
                if rep.get("prenom") and rep.get("nom")
                and _is_director(rep.get("qualite", ""))
            ]
            if not directors:
                continue

            director = directors[0]
            siege = detail.get("siege", {})
            phone = siege.get("telephone") or ""
            website = detail.get("site_web") or ""

            effectif = detail.get("effectif") or company.get("effectif") or ""

            raw_prenom = director.get("prenom", "") or ""
            first_name = raw_prenom.split(",")[0].strip().title()

            leads.append({
                "first_name": first_name,
                "last_name": director.get("nom", "").strip().title(),
                "company": detail.get("nom_entreprise", company.get("nom_entreprise", "")),
                "title": director.get("qualite", ""),
                "sector": sector,
                "company_size": str(effectif),
                "linkedin_url": "",
                "phone": phone,
                "website": website,
                "siren": siren,
                "city": siege.get("ville", ""),
            })

        page += 1

    return leads

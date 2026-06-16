import os
import random
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY")

INDUSTRY_MAP = {
    "construction": "construction",
    "logistique": "logistics and supply chain",
    "distribution": "wholesale",
    "retail": "retail",
    "transport": "transportation/trucking/railroad",
    "industrie": "industrial automation",
    "immobilier": "real estate",
    "restauration": "restaurants",
    "hôtellerie": "hospitality",
    "e-commerce": "internet",
    "agroalimentaire": "food production",
}


def search_people(criteria: dict, exclude_urls: set = None) -> list[dict]:
    """
    Search for people on Apollo. Excludes already-seen linkedin_urls.
    Fetches extra results to account for filtered-out duplicates.
    """
    sector = criteria.get("sector", "").lower()
    industry = INDUSTRY_MAP.get(sector, sector)
    size_min = criteria.get("company_size_min", 20)
    size_max = criteria.get("company_size_max", 200)
    target_count = criteria.get("count", 5)
    exclude_urls = exclude_urls or set()

    leads = []
    page = 1

    while len(leads) < target_count and page <= 5:
        payload = {
            "person_titles": criteria.get("titles", ["CEO", "Directeur Général", "DG", "Gérant"]),
            "organization_num_employees_ranges": [f"{size_min},{size_max}"],
            "q_organization_keyword_tags": [industry] if industry else [],
            "person_locations": [criteria.get("location", "France")],
            "page": page,
            "per_page": min(target_count * 3, 25),
        }

        response = requests.post(
            "https://api.apollo.io/v1/people/search",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": APOLLO_API_KEY,
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise Exception(f"Apollo error {response.status_code}: {response.text}")

        people = response.json().get("people", [])
        if not people:
            break

        for p in people:
            if len(leads) >= target_count:
                break
            linkedin = p.get("linkedin_url", "")
            if linkedin and linkedin in exclude_urls:
                continue
            org = p.get("organization") or {}
            phone_numbers = p.get("phone_numbers") or []
            phone = phone_numbers[0].get("sanitized_number", "") if phone_numbers else ""
            leads.append({
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "company": org.get("name", ""),
                "title": p.get("title", ""),
                "sector": sector,
                "company_size": str(org.get("estimated_num_employees", "")),
                "linkedin_url": linkedin,
                "phone": phone,
            })

        page += 1

    return leads

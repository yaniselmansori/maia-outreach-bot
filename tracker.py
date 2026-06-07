import json
import csv
from datetime import datetime
from pathlib import Path

TRACKER_FILE = Path(__file__).parent / "tracker.json"
EXPORT_FILE = Path(__file__).parent / "approved_messages.csv"


def load_tracker() -> list:
    if TRACKER_FILE.exists():
        return json.loads(TRACKER_FILE.read_text())
    return []


def save_tracker(data: list):
    TRACKER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def log_lead(lead: dict, message: str, version: str, status: str = "pending"):
    data = load_tracker()
    entry = {
        "id": len(data) + 1,
        "timestamp": datetime.now().isoformat(),
        "first_name": lead.get("first_name"),
        "company": lead.get("company"),
        "sector": lead.get("sector"),
        "linkedin_url": lead.get("linkedin_url", ""),
        "version": version,
        "message": message,
        "status": status,  # pending | approved | rejected | edited | sent
    }
    data.append(entry)
    save_tracker(data)
    return entry


def update_status(entry_id: int, status: str, final_message: str = None):
    data = load_tracker()
    for entry in data:
        if entry["id"] == entry_id:
            entry["status"] = status
            if final_message:
                entry["message"] = final_message
            entry["updated_at"] = datetime.now().isoformat()
    save_tracker(data)


def export_approved():
    data = load_tracker()
    approved = [e for e in data if e["status"] == "approved"]

    if not approved:
        return 0

    with open(EXPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["first_name", "company", "linkedin_url", "version", "message"],
        )
        writer.writeheader()
        for entry in approved:
            writer.writerow({
                "first_name": entry["first_name"],
                "company": entry["company"],
                "linkedin_url": entry["linkedin_url"],
                "version": entry["version"],
                "message": entry["message"],
            })

    return len(approved)


def get_stats() -> dict:
    data = load_tracker()
    return {
        "total": len(data),
        "pending": sum(1 for e in data if e["status"] == "pending"),
        "approved": sum(1 for e in data if e["status"] == "approved"),
        "rejected": sum(1 for e in data if e["status"] == "rejected"),
        "sent": sum(1 for e in data if e["status"] == "sent"),
    }

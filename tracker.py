import json
import os
import csv
from datetime import datetime
from pathlib import Path

_LOCAL_FILE = Path("/tmp/tracker.json")
_KV_URL = os.environ.get("KV_REST_API_URL")
_KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")
_KV_KEY = "outreach_tracker"


def _kv_available():
    return bool(_KV_URL and _KV_TOKEN)


def _kv_load() -> list:
    from upstash_redis import Redis
    r = Redis(url=_KV_URL, token=_KV_TOKEN)
    raw = r.get(_KV_KEY)
    return json.loads(raw) if raw else []


def _kv_save(data: list):
    from upstash_redis import Redis
    r = Redis(url=_KV_URL, token=_KV_TOKEN)
    r.set(_KV_KEY, json.dumps(data, ensure_ascii=False))


def load_tracker() -> list:
    if _kv_available():
        return _kv_load()
    if _LOCAL_FILE.exists():
        return json.loads(_LOCAL_FILE.read_text())
    return []


def save_tracker(data: list):
    if _kv_available():
        _kv_save(data)
    else:
        _LOCAL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def log_lead(lead: dict, message: str, version: str, status: str = "pending"):
    data = load_tracker()
    entry = {
        "id": len(data) + 1,
        "timestamp": datetime.now().isoformat(),
        "first_name": lead.get("first_name"),
        "last_name": lead.get("last_name", ""),
        "company": lead.get("company"),
        "sector": lead.get("sector"),
        "title": lead.get("title", ""),
        "linkedin_url": lead.get("linkedin_url", ""),
        "ai_signal": lead.get("ai_signal", ""),
        "version": version,
        "message": message,
        "status": status,
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


def get_editing_entry_id() -> int | None:
    """Return the ID of the entry currently being edited, if any."""
    data = load_tracker()
    for entry in data:
        if entry.get("status") == "editing":
            return entry["id"]
    return None


def set_editing_entry_id(entry_id: int):
    """Mark an entry as being edited (stateless webhook mode)."""
    data = load_tracker()
    for entry in data:
        if entry["id"] == entry_id:
            entry["status"] = "editing"
    save_tracker(data)


def export_approved():
    data = load_tracker()
    approved = [e for e in data if e["status"] == "approved"]
    export_file = Path(__file__).parent / "approved_messages.csv"
    if not approved:
        return 0
    with open(export_file, "w", newline="", encoding="utf-8") as f:
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


def reset_pending() -> int:
    data = load_tracker()
    pending = [e for e in data if e["status"] == "pending"]
    kept = [e for e in data if e["status"] != "pending"]
    save_tracker(kept)
    return len(pending)


def get_stats() -> dict:
    data = load_tracker()
    return {
        "total": len(data),
        "pending": sum(1 for e in data if e["status"] == "pending"),
        "approved": sum(1 for e in data if e["status"] == "approved"),
        "rejected": sum(1 for e in data if e["status"] == "rejected"),
        "sent": sum(1 for e in data if e["status"] == "sent"),
    }

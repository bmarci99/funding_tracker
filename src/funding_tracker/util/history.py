from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger("funding_tracker")


def load_history(path: str | Path) -> Dict[str, Any]:
    """Load history from JSON.  Returns dict with 'items' list."""
    p = Path(path)
    if not p.exists():
        return {"items": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "items" not in data:
            return {"items": []}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load history from {p}: {exc}")
        return {"items": []}


def save_history(path: str | Path, history: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(history, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def prune_history(history: Dict[str, Any], rolling_days: int = 30) -> Dict[str, Any]:
    """Drop entries older than rolling_days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=rolling_days)).isoformat()
    history["items"] = [
        e for e in history["items"]
        if e.get("first_seen", "") >= cutoff
    ]
    return history


def get_seen_ids(history: Dict[str, Any]) -> Set[str]:
    return {e["id"] for e in history.get("items", []) if "id" in e}


def get_seen_hashes(history: Dict[str, Any]) -> Dict[str, str]:
    """Return mapping of id → content_hash for change detection."""
    return {
        e["id"]: e.get("content_hash", "")
        for e in history.get("items", [])
        if "id" in e
    }


def diff_items(
    current_items: List[Dict[str, Any]],
    history: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compare current scrape against history.

    Returns (new_items, changed_items, removed_items).
    """
    seen_ids = get_seen_ids(history)
    seen_hashes = get_seen_hashes(history)
    current_ids = {j["id"] for j in current_items}

    new_items = [j for j in current_items if j["id"] not in seen_ids]
    changed_items = [
        j for j in current_items
        if j["id"] in seen_ids and j.get("content_hash", "") != seen_hashes.get(j["id"], "")
    ]
    removed_ids = seen_ids - current_ids
    removed_items = [
        e for e in history.get("items", [])
        if e.get("id") in removed_ids
    ]

    return new_items, changed_items, removed_items


def record_items(history: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge current items into history (upsert by id)."""
    existing = {e["id"]: e for e in history.get("items", []) if "id" in e}
    for j in items:
        jid = j["id"]
        if jid in existing:
            # preserve first_seen, update everything else
            first_seen = existing[jid].get("first_seen", j.get("first_seen"))
            existing[jid].update(j)
            existing[jid]["first_seen"] = first_seen
        else:
            existing[jid] = j
    history["items"] = list(existing.values())
    return history

from __future__ import annotations

from datetime import datetime
from typing import Any

ACTION_PRIORITY = {
    "blocked": 0,
    "failed": 1,
    "report_failed": 1,
    "report_running": 2,
    "review_required": 3,
    "paused": 4,
}


def _actor(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item.get("actor_id"), "name": item.get("actor_name")}


def _time_key(value: Any) -> float:
    text = str(value or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0

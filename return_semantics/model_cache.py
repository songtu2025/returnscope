from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from return_semantics.model_results import ModelCallResult
from return_semantics.schemas import ModelClassification


class JsonlCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                self._items[item["cache_key"]] = item

    def lock_for(self, cache_key: str) -> threading.Lock:
        with self._lock:
            return self._key_locks.setdefault(
                cache_key,
                threading.Lock(),
            )

    def get(self, cache_key: str) -> ModelCallResult | None:
        with self._lock:
            item = self._items.get(cache_key)
        if item is None:
            return None
        return ModelCallResult(
            classification=ModelClassification.model_validate(item["classification"]),
            model_name=item["model_name"],
            usage=item.get("usage", {}),
            metrics=item.get("metrics", {}),
        )

    def put(self, cache_key: str, result: ModelCallResult) -> None:
        item = {
            "cache_key": cache_key,
            "model_name": result.model_name,
            "usage": result.usage,
            "metrics": result.metrics,
            "classification": result.classification.model_dump(mode="json"),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as cache_file:
                cache_file.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._items[cache_key] = item

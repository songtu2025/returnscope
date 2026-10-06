from __future__ import annotations

import hashlib
import json
from typing import Any


def encode_snapshot(value: dict[str, Any]) -> str:
    """按分类标准导入、发布和漂移比较共用的格式编码快照。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def encoded_snapshot_hash(encoded: str) -> str:
    """对已编码快照计算完整的 UTF-8 SHA256。"""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def snapshot_content_hash(value: dict[str, Any]) -> str:
    """校验或比较不需要保留编码文本的分类标准快照。"""
    return encoded_snapshot_hash(encode_snapshot(value))

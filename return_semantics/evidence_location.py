from __future__ import annotations

import re


def restore_unique_source_excerpt(excerpt: str, source: str) -> str:
    """仅在大小写差异能唯一定位时，还原逐字证据。"""
    if excerpt in source:
        return excerpt
    matches = re.finditer(re.escape(excerpt), source, re.IGNORECASE)
    first = next(matches, None)
    return first.group() if first and next(matches, None) is None else excerpt

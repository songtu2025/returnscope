"""当前人工修正使用的语义条目与原文证据校验。"""

from __future__ import annotations

import re
from typing import Any


class _ReviewSemanticValidation:
    def _validate_added_semantic_items(
        self,
        added_semantic_items: list[dict[str, Any]] | None,
        comment: str,
        valid_label_codes: set[str],
    ) -> None:
        for added in added_semantic_items or []:
            label_code = str(added.get("label_code") or "").strip()
            if label_code not in valid_label_codes:
                raise ValueError("选择的语义标签不存在")
            evidence_text = str(added.get("evidence_text") or "").strip()
            if not self._evidence_exists_in_comment(evidence_text, comment):
                raise ValueError("人工补充项的证据必须来自当前用户反馈")

    @staticmethod
    def _evidence_exists_in_comment(evidence_text: str, comment: str) -> bool:
        words = evidence_text.split()
        if not words:
            return False
        pattern = r"\s+".join(re.escape(word) for word in words)
        return re.search(pattern, comment, flags=re.IGNORECASE) is not None

from __future__ import annotations

from typing import Any


def _report_language(source: dict[str, Any]) -> tuple[str, str, str, str]:
    is_returns = source.get("analysis_context") == "returns"
    return (
        "退货记录" if is_returns else "反馈记录",
        "退货评论" if is_returns else "用户反馈",
        "真实退货率" if is_returns else "总体发生率",
        "退货问题" if is_returns else "用户反馈问题",
    )


def _reason_evidence_ids(reasons: list[dict[str, Any]]) -> list[str]:
    return [f"reason.{reason.get('value') or 'unknown'}" for reason in reasons]

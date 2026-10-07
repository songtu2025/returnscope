from __future__ import annotations

from typing import Any

from web_backend.task_contracts import SEGMENT_USER_LIMIT, TaskPlanConflict


def validate_unresolved_policy(policy: str) -> None:
    if policy not in {"block_all", "run_ready"}:
        raise ValueError("未解决品类策略仅支持 block_all 或 run_ready")


def validate_creation_options(policy: str, max_parallel_segments: int) -> None:
    validate_unresolved_policy(policy)
    if not 1 <= max_parallel_segments <= SEGMENT_USER_LIMIT:
        raise ValueError("Listing 并行数必须在 1 到 3 之间")


def validate_creation_plan(response: dict[str, Any], plan_hash: str | None) -> str:
    current_hash = str(response["plan_hash"])
    if plan_hash is not None and plan_hash != current_hash:
        raise TaskPlanConflict("执行计划已变化，请重新预检后再创建任务")
    missing_category_comments = int(response.get("missing_category_comment_count", 0))
    if missing_category_comments:
        raise ValueError(
            "所选数据中有 "
            f"{missing_category_comments} 条有效评论对应商品缺少品类A或品类B，"
            "请先补齐商品目录后再创建任务"
        )
    return current_hash


def initial_creation_state(
    planned_segments: list[dict[str, Any]], block_all: bool
) -> tuple[str, str, str]:
    if not planned_segments:
        return (
            "completed",
            "分析完成",
            "本次数据均为不分析记录，未创建 Listing 执行片段",
        )
    return (
        "blocked" if block_all else "queued",
        "等待品类处理" if block_all else "等待运行",
        (
            "存在未解决品类，等待补充或调整处理策略"
            if block_all
            else "任务已进入 Listing 队列"
        ),
    )

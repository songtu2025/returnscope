"""只记录错误类型和代码位置，不记录异常原文、SQL 或模型载荷。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from traceback import extract_tb

from web_backend.common import json_text

logger = logging.getLogger("uvicorn.error.task_execution")


def log_segment_failure(
    task_id: str, segment_id: str | None, phase: str, error: BaseException
) -> None:
    root = error
    seen = {id(root)}
    while root.__cause__ is not None and id(root.__cause__) not in seen:
        root = root.__cause__
        seen.add(id(root))
    frames = extract_tb(root.__traceback__)
    origin = frames[-1] if frames else None
    details = {
        "task_id": task_id,
        "segment_id": segment_id,
        "phase": phase,
        "error_type": type(error).__name__,
        "root_error_type": type(root).__name__,
        "source": f"{Path(origin.filename).name}:{origin.name}:{origin.lineno}"
        if origin
        else None,
        "sqlite_code": getattr(root, "sqlite_errorcode", None)
        if isinstance(root, sqlite3.Error)
        else None,
    }
    logger.error("segment_failure %s", json_text(details))

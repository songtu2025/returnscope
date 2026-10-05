from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException


@contextmanager
def task_request_errors(*conflicts: type[Exception]) -> Iterator[None]:
    """只将当前端点明确指定的冲突类型转换为业务冲突。"""
    try:
        yield
    except conflicts as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@contextmanager
def task_analysis_errors() -> Iterator[None]:
    """分析与筛选导出共用任务不存在和未就绪的错误映射。"""
    try:
        yield
    except ValueError as exc:
        status_code = 404 if str(exc) == "任务不存在" else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

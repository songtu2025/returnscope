from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException


def require_model_admin(user: dict[str, Any]) -> None:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="仅系统管理员可维护模型服务")


@contextmanager
def model_request_errors() -> Iterator[None]:
    """保持模型维护接口的业务错误转换一致。"""
    try:
        yield
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

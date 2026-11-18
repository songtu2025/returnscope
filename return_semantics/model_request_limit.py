from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_remaining_attempts: ContextVar[int | None] = ContextVar(
    "remaining_model_request_attempts", default=None
)


@contextmanager
def model_request_limit(attempts: int) -> Iterator[None]:
    """在当前反馈范围内共享实际请求预算，包含服务重试。"""
    token = _remaining_attempts.set(attempts)
    try:
        yield
    finally:
        _remaining_attempts.reset(token)


def has_model_request_budget() -> bool:
    remaining = _remaining_attempts.get()
    return remaining is None or remaining > 0


def claim_model_request() -> None:
    remaining = _remaining_attempts.get()
    if remaining is None:
        return
    if remaining == 0:
        raise RuntimeError("本条反馈已用完模型请求额度")
    _remaining_attempts.set(remaining - 1)

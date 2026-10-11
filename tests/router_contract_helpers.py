from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, kw_only=True)
class RouteCase:
    service_method: str
    path: str
    method: str = "GET"
    request: dict[str, Any] = field(default_factory=dict)
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    status: int = 200

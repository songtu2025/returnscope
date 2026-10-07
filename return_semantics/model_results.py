from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from return_semantics.schemas import ModelClassification


class ModelClientSettings(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def secondary_model(self) -> str | None: ...

    @property
    def cheap_model(self) -> str | None: ...

    @property
    def cheap_model_audit_percent(self) -> int: ...

    @property
    def max_workers(self) -> int: ...

    @property
    def provider(self) -> str: ...

    @property
    def cache_namespace(self) -> str: ...


class ModelClient(Protocol):
    @property
    def settings(self) -> ModelClientSettings: ...

    def classify(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        thinking: bool = False,
    ) -> "ModelCallResult": ...


@dataclass(frozen=True)
class ModelCallResult:
    classification: ModelClassification
    model_name: str
    usage: dict[str, int]
    metrics: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class JsonModelCallResult:
    payload: dict[str, Any]
    model_name: str
    usage: dict[str, int]
    metrics: dict[str, int] = field(default_factory=dict)

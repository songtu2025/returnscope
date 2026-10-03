from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from return_semantics.schemas import ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.database import Database


class _ReviewEditingContext:
    database: Database

    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def get(self, review_id: str) -> dict[str, Any] | None: ...

        def get_batch(self, batch_id: str) -> dict[str, Any]: ...

        def _record_batch_conflict(
            self,
            batch_id: str,
            actor_id: str,
            message: str,
        ) -> None: ...

        def _validate_reviewed_classification(
            self,
            classification: dict[str, Any],
        ) -> tuple[ValidatedClassification, dict[str, Any]]: ...

        _insert_audit: Callable[
            [Any, str, str, str, dict[str, Any], dict[str, Any], str],
            None,
        ]

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.database import Database


class _ReviewEditingContext:
    database: Database

    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def _validate_reviewed_classification(
            self,
            classification: dict[str, Any],
        ) -> tuple[ValidatedClassification, dict[str, Any]]: ...

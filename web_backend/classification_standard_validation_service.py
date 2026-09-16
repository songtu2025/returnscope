from __future__ import annotations

from typing import TYPE_CHECKING

from web_backend import classification_standard_validation_contracts as _contracts
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_execution import (
    ClassificationStandardValidationExecutionMixin,
)
from web_backend.classification_standard_validation_lifecycle import (
    ClassificationStandardValidationLifecycleMixin,
)
from web_backend.classification_standard_validation_queries import (
    ClassificationStandardValidationQueriesMixin,
)
from web_backend.classification_standard_validation_review_source import (
    ClassificationStandardValidationReviewSourceMixin,
)
from web_backend.classification_standard_validation_sources import (
    ClassificationStandardValidationSourcesMixin,
)
from web_backend.database import Database

if TYPE_CHECKING:
    from web_backend.agent_runner import AgentRunner

ClassificationStandardValidationNotFound = (
    _contracts.ClassificationStandardValidationNotFound
)
ClassificationStandardValidationConflict = (
    _contracts.ClassificationStandardValidationConflict
)

ClassificationStandardValidationNotFound.__module__ = __name__
ClassificationStandardValidationConflict.__module__ = __name__


class ClassificationStandardValidationService(
    ClassificationStandardValidationQueriesMixin,
    ClassificationStandardValidationLifecycleMixin,
    ClassificationStandardValidationExecutionMixin,
    ClassificationStandardValidationSourcesMixin,
    ClassificationStandardValidationReviewSourceMixin,
):
    def __init__(
        self,
        database: Database,
        standard_service: ClassificationStandardService,
        runner: AgentRunner,
    ) -> None:
        self.database = database
        self.standard_service = standard_service
        self.runner = runner

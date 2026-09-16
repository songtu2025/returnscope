from __future__ import annotations

from typing import Any

CLASSIFICATION_STANDARD_SEED_MIGRATION = "20260824_01_seed_classification_standards"
CLASSIFICATION_STANDARD_RULES_MIGRATION = "20260825_01_embed_taxonomy_validation_rules"


class ClassificationStandardNotFound(ValueError):
    pass


class ClassificationStandardConflict(ValueError):
    pass


class ClassificationStandardValidationError(ValueError):
    def __init__(self, validation: dict[str, Any]) -> None:
        self.validation = validation
        super().__init__("分类标准未通过发布检查")

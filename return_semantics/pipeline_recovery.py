"""统一分类失败和复核降级时的结果与诊断。"""

from return_semantics.pipeline_models import _PipelineContext
from return_semantics.prompt import prompt_version
from return_semantics.schemas import (
    ProcessingStatus,
    ReviewDiagnostic,
    ValidatedClassification,
)


def _is_timeout_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        message = str(current).casefold()
        if isinstance(current, TimeoutError) or any(
            marker in message for marker in ("timeout", "timed out", "超时")
        ):
            return True
        current = current.__cause__
    return False


def _model_error(
    context: _PipelineContext,
    classification_key: str,
    exc: Exception,
) -> ValidatedClassification:
    return ValidatedClassification(
        classification_key=classification_key,
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.MODEL_ERROR,
        review_reasons=[str(exc)],
        review_diagnostics=[
            ReviewDiagnostic(
                code=(
                    "MODEL_RUN_TIMEOUT"
                    if _is_timeout_error(exc)
                    else "MODEL_RUN_FAILED"
                ),
                detail=str(exc),
                action="SYSTEM_RERUN",
            )
        ],
        model_name=context.client.settings.model,
        prompt_version=prompt_version(context.taxonomy),
        taxonomy_version=context.taxonomy.version,
    )


def _mark_secondary_fallback(
    context: _PipelineContext,
    validated: ValidatedClassification,
) -> ValidatedClassification:
    if not context.secondary_is_fallback:
        return validated
    return validated.model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_reasons": validated.review_reasons
            + ["风险复核模型缺失，已使用主模型复核"],
            "review_diagnostics": validated.review_diagnostics
            + [
                ReviewDiagnostic(
                    code="SECONDARY_MODEL_MISSING",
                    detail="风险复核模型缺失，已使用主模型复核",
                    action="ADMIN_CONFIG",
                )
            ],
        }
    )

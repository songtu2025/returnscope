from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from return_semantics.model_client import ModelCallResult, ModelClient
from return_semantics.pipeline_models import _PipelineContext, _RowContext
from return_semantics.prompt import (
    PROMPT_VERSION,
    prompt_version,
    recognition_fingerprint,
)
from return_semantics.semantic_review import requires_system_rerun


def build_cache_key(
    comment: str,
    model_name: str,
    provider_name: str,
    taxonomy_version: str,
    claims_version: str,
    thinking: bool = False,
    classification_scope: str = "",
    reasoning_effort: str = "",
    model_policy_version: str = "legacy-model-policy-v1",
    recognition_key: str = "",
    effective_prompt_version: str = PROMPT_VERSION,
) -> str:
    payload = {
        "comment": comment.lower(),
        "model": f"{model_name}:thinking" if thinking else model_name,
        "prompt": effective_prompt_version,
        "taxonomy": taxonomy_version,
        "claims": claims_version,
        "scope": classification_scope,
        "effort": reasoning_effort,
        "model_policy": model_policy_version,
    }
    if recognition_key:
        payload["recognition"] = recognition_key
    payload["provider"] = provider_name
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _model_reasoning_effort(
    client: ModelClient, model_name: str, thinking: bool
) -> Any:
    if thinking:
        return getattr(client.settings, "secondary_reasoning_effort", "")
    if model_name == getattr(client.settings, "cheap_model", None):
        return getattr(client.settings, "cheap_reasoning_effort", "")
    return getattr(client.settings, "reasoning_effort", "")


def _cache_key_for_row(
    row: _RowContext,
    context: _PipelineContext,
    model_name: str,
    thinking: bool,
    reasoning_effort: Any,
) -> str:
    return build_cache_key(
        comment=row.comment,
        model_name=model_name,
        provider_name=context.client.settings.cache_namespace,
        taxonomy_version=context.taxonomy.version,
        claims_version=context.claims.version,
        effective_prompt_version=prompt_version(context.taxonomy),
        recognition_key=(
            recognition_fingerprint(context.taxonomy)
            if context.taxonomy.recognition_profile != "legacy_v3"
            else ""
        ),
        thinking=thinking,
        classification_scope=row.classification_scope,
        reasoning_effort=str(reasoning_effort),
        model_policy_version=context.model_policy_version,
    )


def call_with_cache(
    row: _RowContext,
    context: _PipelineContext,
    model_name: str,
    thinking: bool,
    *,
    classify_uncached: Callable[
        [_RowContext, _PipelineContext, str, bool, Any], ModelCallResult
    ],
) -> tuple[ModelCallResult, bool]:
    reasoning_effort = _model_reasoning_effort(context.client, model_name, thinking)
    cache_key = _cache_key_for_row(row, context, model_name, thinking, reasoning_effort)
    with context.cache.lock_for(cache_key):
        cached = None if context.force else context.cache.get(cache_key)
        if cached is not None and not requires_system_rerun(
            cached.classification,
            row.comment,
            context.taxonomy,
        ):
            return cached, True
        result = classify_uncached(row, context, model_name, thinking, reasoning_effort)
        if not requires_system_rerun(
            result.classification, row.comment, context.taxonomy
        ):
            context.cache.put(cache_key, result)
        return result, False

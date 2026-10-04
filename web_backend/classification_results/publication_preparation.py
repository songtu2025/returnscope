from __future__ import annotations

from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_result_payload import (
    _classification_quality,
    _nullable_text,
    _prepare_classification_payload,
)


def prepare_publication(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> dict[str, Any]:
    comments = dataset.unique_comments.set_index("classification_key")
    units = [
        prepare_unit(key, results[key], comments.loc[key], taxonomy)
        for key in sorted(results)
    ]
    labels = prepare_labels(results, taxonomy)
    quality_by_key = {
        unit["classification_key"]: unit["quality_status"] for unit in units
    }
    records = prepare_records(dataset, results, quality_by_key)
    scopes = {(value["store_site"], value["listing"]) for value in records}
    store_site, listing = next(iter(scopes)) if len(scopes) == 1 else (None, None)
    return {
        "units": units,
        "labels": labels,
        "records": records,
        "store_site": store_site,
        "listing": listing,
    }


def prepare_unit(
    key: str,
    result: ValidatedClassification,
    source: Any,
    taxonomy: TaxonomyConfig,
) -> dict[str, Any]:
    processing_status = result.status.value
    classification = _prepare_classification_payload(
        result.model_dump(mode="json"),
        taxonomy,
        processing_status,
        include_api_fields=False,
    )
    quality_status = _classification_quality(
        result,
        str(classification["semantic_disposition"]),
        source_text=str(source.get("comment_normalized") or ""),
        taxonomy=taxonomy,
    )
    classification.pop("semantic_disposition", None)
    for semantic_unit in classification.get("semantic_units", []):
        semantic_unit.pop("label_code_path", None)
        semantic_unit.pop("label_path", None)
    return {
        "classification_key": key,
        "reason": _nullable_text(source.get("reason")),
        "comment": _nullable_text(source.get("comment_normalized")),
        "classification": classification,
        "problem_labels": list(result.problem_label_codes),
        "processing_status": processing_status,
        "quality_status": quality_status,
        "record_count": int(source.get("record_count", 0)),
        "model_name": result.model_name,
        "prompt_version": result.prompt_version,
        "taxonomy_version": result.taxonomy_version,
    }


def prepare_labels(
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, Any]]:
    label_map = {label.code: label for label in taxonomy.labels}
    labels: list[dict[str, Any]] = []
    for key in sorted(results):
        result = results[key]
        for kind, codes in (
            ("problem", result.problem_label_codes),
            ("positive", result.positive_label_codes),
            ("primary", result.primary_label_codes),
        ):
            for code in sorted(set(codes)):
                label = label_map.get(code)
                labels.append(
                    {
                        "classification_key": key,
                        "label_kind": kind,
                        "label_code": code,
                        "label_name": label.name if label else None,
                        "label_group": label.group if label else None,
                    }
                )
    return labels


def prepare_records(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    quality_by_key: dict[str, str],
) -> list[dict[str, Any]]:
    selected = dataset.records.loc[
        dataset.records["classification_key"].isin(results)
    ].copy()
    records: list[dict[str, Any]] = []
    for row in selected.sort_values("source_row").to_dict(orient="records"):
        classification_key = str(row["classification_key"])
        records.append(
            {
                "classification_key": classification_key,
                "source_row": int(row["source_row"]),
                "source_origin_id": _nullable_text(row.get("source-origin-id")),
                "return_date": _nullable_text(row.get("return-date")),
                "order_id": _nullable_text(row.get("order-id")),
                "store_site": _nullable_text(row.get("store")),
                "listing": _nullable_text(row.get("listing")),
                "product_name": _nullable_text(row.get("product_name")),
                "source_sku": _nullable_text(row.get("source_sku")),
                "matched_msku": _nullable_text(row.get("matched_msku")),
                "product_sku": _nullable_text(row.get("product_sku")),
                "asin": _nullable_text(row.get("asin")),
                "fnsku": _nullable_text(row.get("fnsku")),
                "category_a": _nullable_text(row.get("category_a")),
                "category_b": _nullable_text(row.get("category_b")),
                "reason": _nullable_text(row.get("reason")),
                "comment": _nullable_text(row.get("comment_raw")),
                "product_match_status": str(
                    row.get("product_match_status") or "unmatched"
                ),
                "quality_status": quality_by_key[classification_key],
            }
        )
    return records

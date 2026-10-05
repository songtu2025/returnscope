from __future__ import annotations

from typing import Any

from return_semantics.capabilities import CapabilityRegistry
from return_semantics.task_plan import CategoryExecutionPlan


def model_configuration(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_model": config["primary_model"],
        "primary_effort": config["primary_effort"],
        "cheap_model": config["cheap_model"],
        "cheap_effort": config["cheap_effort"],
        "secondary_model": config["secondary_model"],
        "secondary_effort": config["secondary_effort"],
    }


def bind_standard_versions(
    execution_plan: CategoryExecutionPlan, standards: dict[str, dict[str, Any]]
) -> CategoryExecutionPlan:
    return CategoryExecutionPlan(
        summary={
            **execution_plan.summary,
            "segments": [
                {
                    **segment,
                    "standard_id": standards.get(str(segment["agent_key"]), {}).get(
                        "standard_id"
                    ),
                    "standard_version_id": standards.get(
                        str(segment["agent_key"]), {}
                    ).get("standard_version_id"),
                    "standard_name": standards.get(str(segment["agent_key"]), {}).get(
                        "name"
                    ),
                    "standard_version": standards.get(
                        str(segment["agent_key"]), {}
                    ).get("version_no"),
                }
                for segment in execution_plan.summary["segments"]
            ],
        },
        assignments=execution_plan.assignments,
    )


def input_versions(
    returns: dict[str, Any], products: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "returns": {"version_id": returns["id"], "sha256": returns["sha256"]},
        "products": {"version_id": products["id"], "sha256": products["sha256"]},
        "config": {
            "version_id": config["id"],
            "version": config["version"],
            **model_configuration(config),
        },
    }


def unresolved_product_counts(
    unresolved_products: list[dict[str, Any]],
    missing_category_products: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "unresolved_product_count": len(unresolved_products),
        "unresolved_products": unresolved_products,
        "category_completion_required": bool(missing_category_products),
        "missing_category_product_count": len(missing_category_products),
        "missing_category_product_record_count": sum(
            (int(item["record_count"]) for item in missing_category_products)
        ),
        "missing_category_comment_count": sum(
            (int(item["comment_count"]) for item in missing_category_products)
        ),
        "unresolved_product_comment_count": sum(
            (int(item["comment_count"]) for item in unresolved_products)
        ),
    }


def category_options(
    registry: CapabilityRegistry, standards: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "category_a": variant.category_a,
            "category_b": variant.category_b,
            "agent_family": capability.agent_family,
            "standard_id": standards.get(capability.key, {}).get("standard_id"),
            "standard_version_id": standards.get(capability.key, {}).get(
                "standard_version_id"
            ),
            "standard_name": standards.get(capability.key, {}).get("name"),
            "standard_version": standards.get(capability.key, {}).get("version_no"),
        }
        for capability in registry.capabilities
        for variant in capability.variants
    ]

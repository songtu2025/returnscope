from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from return_semantics.capabilities import (
    CapabilityRegistry,
    load_capability_registry,
)
from return_semantics.claims import ClaimsResolver
from return_semantics.data import (
    ReturnDataset,
    load_product_dimensions,
    load_return_dataset,
    load_return_dataset_auto,
)
from return_semantics.task_plan import (
    CategoryExecutionPlan,
    build_category_execution_plan,
)
from web_backend.database import Database
from web_backend.settings import PROJECT_ROOT


@dataclass(frozen=True)
class PreparedTaskPlan:
    returns: dict[str, Any]
    products: dict[str, Any]
    config: dict[str, Any]
    dataset: ReturnDataset
    execution_plan: CategoryExecutionPlan
    response: dict[str, Any]


class TaskPlanService:
    def __init__(
        self,
        database: Database,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self.database = database
        self.registry = registry or load_capability_registry(
            PROJECT_ROOT / "config" / "category_capabilities.json"
        )
        self.claims_resolver = ClaimsResolver(
            PROJECT_ROOT / "config" / "listing_claims_registry.json"
        )

    def preflight(
        self,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.prepare(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
        ).response

    def prepare(
        self,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
    ) -> PreparedTaskPlan:
        clean_store = (store or "").strip()
        clean_listing = (listing or "").strip() or None
        returns, products, config = self._load_inputs(
            dataset_version_id,
            product_version_id,
            config_version_id,
        )
        if model_policy is not None:
            config = self._apply_model_policy(config, model_policy)
        automatic_scope = not clean_store
        if automatic_scope:
            dataset = load_return_dataset_auto(
                Path(str(returns["file_path"])),
                Path(str(products["file_path"])),
            )
            clean_store = dataset.primary_store or "AUTO"
            clean_listing = None
        else:
            dataset = load_return_dataset(
                Path(str(returns["file_path"])),
                Path(str(products["file_path"])),
                store=clean_store,
                listing=clean_listing,
            )
        model_config = {
            "primary_model": config["primary_model"],
            "primary_effort": config["primary_effort"],
            "cheap_model": config["cheap_model"],
            "cheap_effort": config["cheap_effort"],
            "secondary_model": config["secondary_model"],
            "secondary_effort": config["secondary_effort"],
        }
        execution_plan = build_category_execution_plan(
            dataset,
            self.registry,
            store=clean_store,
            listing=clean_listing,
            model_config=model_config,
            claims_resolver=self.claims_resolver,
        )
        unresolved_products = self._unresolved_products(
            dataset,
            execution_plan,
            Path(str(products["file_path"])),
            clean_store,
            clean_listing,
        )
        missing_category_products = [
            item for item in unresolved_products if item["issue"] == "missing_category"
        ]
        inputs = {
            "returns": {
                "version_id": returns["id"],
                "sha256": returns["sha256"],
            },
            "products": {
                "version_id": products["id"],
                "sha256": products["sha256"],
            },
            "config": {
                "version_id": config["id"],
                "version": config["version"],
                "primary_model": config["primary_model"],
                "primary_effort": config["primary_effort"],
                "cheap_model": config["cheap_model"],
                "cheap_effort": config["cheap_effort"],
                "secondary_model": config["secondary_model"],
                "secondary_effort": config["secondary_effort"],
            },
            "scope": {
                "mode": "auto" if automatic_scope else "manual",
                "store": clean_store,
                "listing": clean_listing,
                "detected_scopes": list(dataset.scopes),
            },
        }
        response = {
            **execution_plan.with_hash(inputs),
            "inputs": inputs,
            "unresolved_product_count": len(unresolved_products),
            "unresolved_products": unresolved_products,
            "category_completion_required": bool(missing_category_products),
            "missing_category_product_count": len(missing_category_products),
            "missing_category_product_record_count": sum(
                int(item["record_count"]) for item in missing_category_products
            ),
            "missing_category_comment_count": sum(
                int(item["comment_count"]) for item in missing_category_products
            ),
            "unresolved_product_comment_count": sum(
                int(item["comment_count"]) for item in unresolved_products
            ),
            "category_options": [
                {
                    "category_a": variant.category_a,
                    "category_b": variant.category_b,
                    "agent_family": capability.agent_family,
                }
                for capability in self.registry.capabilities
                for variant in capability.variants
            ],
        }
        return PreparedTaskPlan(
            returns=returns,
            products=products,
            config=config,
            dataset=dataset,
            execution_plan=execution_plan,
            response=response,
        )

    @staticmethod
    def _suggest_listing(sku: str, listings: list[str]) -> str:
        candidates = [
            value
            for value in listings
            if sku == value
            or sku.startswith(f"{value}-")
            or sku.startswith(f"{value}_")
            or sku.startswith(f"{value} ")
        ]
        return max(candidates, key=len) if candidates else ""

    def _unresolved_products(
        self,
        dataset: ReturnDataset,
        execution_plan: CategoryExecutionPlan,
        product_path: Path,
        store: str,
        listing: str | None,
    ) -> list[dict[str, Any]]:
        unresolved_keys = set(execution_plan.unresolved_classification_keys(dataset))
        missing_category_keys = {
            str(row.classification_key)
            for assignment, row in zip(
                execution_plan.assignments,
                dataset.unique_comments.itertuples(index=False),
                strict=True,
            )
            if assignment == "excluded"
        }
        resolution_keys = unresolved_keys | missing_category_keys
        if not resolution_keys:
            return []
        blocked = dataset.records.loc[
            dataset.records["has_text_evidence"]
            & dataset.records["classification_key"].isin(resolution_keys)
        ].copy()
        fallback_store = "" if store == "AUTO" else store
        context_by_store: dict[
            str,
            tuple[frozenset[str], list[str], dict[str, str]],
        ] = {}

        def store_context(
            scope_store: str,
        ) -> tuple[
            frozenset[str],
            list[str],
            dict[str, str],
        ]:
            if not scope_store:
                return frozenset(), [], {}
            if scope_store not in context_by_store:
                scope_listing = listing if dataset.scope_mode == "manual" else None
                dimensions = load_product_dimensions(
                    product_path,
                    scope_store,
                    scope_listing,
                )
                listings = sorted(
                    value for value in dimensions["Listing"].unique().tolist() if value
                )
                listing_by_msku = (
                    dimensions.loc[
                        dimensions["MSKU"].ne(""),
                        ["MSKU", "Listing"],
                    ]
                    .drop_duplicates(subset=["MSKU"])
                    .set_index("MSKU")["Listing"]
                    .to_dict()
                )
                context_by_store[scope_store] = (
                    frozenset(dimensions["MSKU"]),
                    listings,
                    listing_by_msku,
                )
            return context_by_store[scope_store]

        output = []
        for (row_store, sku), rows in blocked.groupby(
            ["store", "sku"],
            sort=True,
            dropna=False,
        ):
            scope_store = str(row_store).strip() or fallback_store
            clean_sku = str(sku).strip()
            store_mskus, listings, listing_by_msku = store_context(scope_store)
            category_a = str(rows["category_a"].iloc[0]).strip()
            category_b = str(rows["category_b"].iloc[0]).strip()
            product_names = [
                str(value).strip()
                for value in rows["product_name"].tolist()
                if str(value).strip().lower() not in {"", "nan", "none"}
            ]
            existing = clean_sku in store_mskus
            if not clean_sku:
                issue = "missing_product_key"
            elif existing and not category_a and not category_b:
                issue = "missing_category"
            elif existing:
                issue = "unsupported_category"
            else:
                issue = "product_not_found"
            suggested_listing = str(
                listing_by_msku.get(clean_sku)
                or self._suggest_listing(clean_sku, listings)
            )
            item = {
                "product_key": (
                    f"{scope_store}/{clean_sku}"
                    if dataset.scope_mode == "auto" and scope_store
                    else clean_sku
                ),
                "store": scope_store,
                "msku": clean_sku,
                "product_name": product_names[0] if product_names else "",
                "current_category_a": category_a,
                "current_category_b": category_b,
                "suggested_listing": suggested_listing,
                "record_count": len(rows),
                "comment_count": int(rows["classification_key"].nunique()),
                "issue": issue,
                "existing_product": existing,
                "editable": bool(scope_store and clean_sku),
            }
            output.append(item)
        return sorted(
            output,
            key=lambda item: (
                -int(item["comment_count"]),
                -int(item["record_count"]),
                str(item["store"]),
                str(item["msku"]),
            ),
        )

    def _load_inputs(
        self,
        dataset_version_id: str,
        product_version_id: str,
        config_version_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        with self.database.connect() as connection:
            returns_row = connection.execute(
                """
                SELECT v.*, d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (dataset_version_id,),
            ).fetchone()
            products_row = connection.execute(
                """
                SELECT v.*, d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (product_version_id,),
            ).fetchone()
            if config_version_id:
                config_row = connection.execute(
                    """
                    SELECT v.*, c.name AS connection_name,
                           c.active_version_id
                    FROM api_config_versions v
                    JOIN api_connections c ON c.id = v.connection_id
                    WHERE v.id = ?
                    """,
                    (config_version_id,),
                ).fetchone()
            else:
                config_row = connection.execute(
                    """
                    SELECT v.*, c.name AS connection_name,
                           c.active_version_id
                    FROM api_connections c
                    JOIN api_config_versions v ON v.id = c.active_version_id
                    ORDER BY c.updated_at DESC LIMIT 1
                    """
                ).fetchone()
        if returns_row is None or returns_row["kind"] != "returns":
            raise ValueError("请选择有效的退货数据版本")
        if products_row is None or products_row["kind"] != "products":
            raise ValueError("请选择有效的商品维度版本")
        if config_row is None or config_row["published_at"] is None:
            raise ValueError("请先验证并发布一个 API 配置")
        return dict(returns_row), dict(products_row), dict(config_row)

    def _apply_model_policy(
        self,
        config: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        connection_id = str(policy.get("connection_id") or "")
        if connection_id != str(config["connection_id"]):
            raise ValueError("本次模型策略与所选模型服务连接不一致")
        values = {
            "cheap_model": (policy.get("cheap_model") or "").strip() or None,
            "cheap_effort": str(policy.get("cheap_effort") or "low"),
            "primary_model": str(policy.get("primary_model") or "").strip(),
            "primary_effort": str(policy.get("primary_effort") or "medium"),
            "secondary_model": (policy.get("secondary_model") or "").strip() or None,
            "secondary_effort": str(policy.get("secondary_effort") or "high"),
            "cheap_audit_percent": int(policy.get("cheap_audit_percent", 5)),
        }
        if not values["primary_model"]:
            raise ValueError("主分析模型不能为空")
        with self.database.connect() as connection:
            active = connection.execute(
                "SELECT active_version_id FROM api_connections WHERE id = ?",
                (connection_id,),
            ).fetchone()
            if active is None or str(active["active_version_id"] or "") != str(
                config["id"]
            ):
                raise ValueError("请选择当前已发布的模型服务连接")
            for model_key, effort in (
                (values["cheap_model"], values["cheap_effort"]),
                (values["primary_model"], values["primary_effort"]),
                (values["secondary_model"], values["secondary_effort"]),
            ):
                if not model_key:
                    continue
                row = connection.execute(
                    """
                    SELECT display_name, supported_efforts_json, active, validation_status
                    FROM api_models WHERE connection_id = ? AND model_key = ?
                    """,
                    (connection_id, model_key),
                ).fetchone()
                if row is None or not row["active"]:
                    raise ValueError(f"模型 {model_key} 不可用")
                if row["validation_status"] != "validated":
                    raise ValueError(f"模型 {row['display_name']} 必须先验证通过")
                if effort not in json.loads(row["supported_efforts_json"]):
                    raise ValueError(
                        f"模型 {row['display_name']} 不支持 {effort} 推理强度"
                    )
        return {**config, **values}

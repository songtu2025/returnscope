from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from return_semantics.analysis_context import USER_FEEDBACK_CONTEXT, AnalysisContext
from return_semantics.capabilities import CapabilityRegistry
from return_semantics.claims import ClaimsResolver
from return_semantics.data import ReturnDataset
from return_semantics.task_plan import (
    CategoryExecutionPlan,
    build_category_execution_plan,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.database import Database
from web_backend.dataset_cache import load_cached_dataset
from web_backend.settings import PROJECT_ROOT
from web_backend.tasks.plan_inputs import TaskPlanInputsMixin
from web_backend.tasks.plan_response import (
    bind_standard_versions,
    category_options,
    input_versions,
    model_configuration,
    unresolved_product_counts,
)
from web_backend.tasks.product_resolution import TaskProductResolutionMixin


@dataclass(frozen=True)
class PreparedTaskPlan:
    returns: dict[str, Any]
    products: dict[str, Any]
    config: dict[str, Any]
    dataset: ReturnDataset
    execution_plan: CategoryExecutionPlan
    response: dict[str, Any]


class TaskPlanService(TaskPlanInputsMixin, TaskProductResolutionMixin):
    def __init__(
        self,
        database: Database,
        registry: CapabilityRegistry | None = None,
        standard_service: ClassificationStandardService | None = None,
    ) -> None:
        self.database = database
        self.standard_service = standard_service or ClassificationStandardService(
            database
        )
        self.registry = registry
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
        analysis_context: AnalysisContext = USER_FEEDBACK_CONTEXT,
    ) -> dict[str, Any]:
        return self.prepare(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
            analysis_context=analysis_context,
        ).response

    def prepare(
        self,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
        analysis_context: AnalysisContext = USER_FEEDBACK_CONTEXT,
    ) -> PreparedTaskPlan:
        clean_store = (store or "").strip()
        clean_listing = (listing or "").strip() or None
        returns, products, config = self._load_inputs(
            dataset_version_id, product_version_id, config_version_id
        )
        if model_policy is not None:
            config = self._apply_model_policy(config, model_policy)
        automatic_scope = not clean_store
        dataset, clean_store, clean_listing = self._dataset_scope(
            returns, products, (clean_store, clean_listing), analysis_context
        )
        model_config = model_configuration(config)
        registry = self.registry or self.standard_service.active_registry()
        execution_plan = build_category_execution_plan(
            dataset,
            registry,
            store=clean_store,
            listing=clean_listing,
            model_config=model_config,
            claims_resolver=self.claims_resolver,
        )
        standards = self.standard_service.current_version_by_agent()
        execution_plan = bind_standard_versions(execution_plan, standards)
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
            "analysis_context": analysis_context,
            **input_versions(returns, products, config),
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
            **unresolved_product_counts(unresolved_products, missing_category_products),
            "category_options": category_options(registry, standards),
        }
        return PreparedTaskPlan(
            returns=returns,
            products=products,
            config=config,
            dataset=dataset,
            execution_plan=execution_plan,
            response=response,
        )

    def _dataset_scope(
        self,
        returns: dict[str, Any],
        products: dict[str, Any],
        scope: tuple[str, str | None],
        analysis_context: AnalysisContext,
    ) -> tuple[ReturnDataset, str, str | None]:
        clean_store, clean_listing = scope
        automatic_scope = not clean_store
        dataset = load_cached_dataset(
            str(returns["file_path"]),
            str(products["file_path"]),
            clean_store,
            clean_listing,
            "auto" if automatic_scope else "manual",
            str(returns["sha256"]),
            str(products["sha256"]),
            analysis_context,
        )
        if automatic_scope:
            clean_store = dataset.primary_store or "AUTO"
            clean_listing = None
        return (dataset, clean_store, clean_listing)

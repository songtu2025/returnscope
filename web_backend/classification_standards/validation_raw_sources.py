from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, SupportsInt, cast

from return_semantics.data import ReturnDataset, load_return_dataset_auto
from web_backend.database import Database


class ClassificationStandardValidationRawSourcesMixin:
    database: Database

    if TYPE_CHECKING:

        def _published_config_id(self) -> str: ...

        @staticmethod
        def _round_robin_samples(
            items: list[dict[str, Any]],
            sample_size: int,
            *,
            bucket_fields: tuple[str, ...],
        ) -> list[dict[str, Any]]: ...

    def _raw_source_options(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.id AS version_id, v.version, v.file_path,
                       v.row_count, v.created_at, d.name AS dataset_name,
                       d.kind
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.archived_at IS NULL
                  AND d.kind IN ('returns', 'products')
                  AND (d.kind = 'products' OR d.usage_scope = 'task_input')
                ORDER BY v.created_at DESC, v.id
                """
            ).fetchall()
        returns = [dict(row) for row in rows if row["kind"] == "returns"]
        products = [dict(row) for row in rows if row["kind"] == "products"]
        output = []
        for return_version in returns:
            for product_version in products:
                source_key = "\x1f".join(
                    [return_version["version_id"], product_version["version_id"]]
                )
                source_id = (
                    "raw_validation_"
                    + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
                )
                output.append(
                    {
                        "id": source_id,
                        "return": return_version,
                        "product": product_version,
                        "public": {
                            "result_version_id": source_id,
                            "source_kind": "raw_dataset",
                            "version_no": int(return_version["version"]),
                            "quality_status": "raw",
                            "unit_count": 0,
                            "record_count": int(return_version["row_count"]),
                            "published_at": return_version["created_at"],
                            "store_site": "",
                            "listing": "",
                            "available_sample_count": None,
                            "return_dataset_name": return_version["dataset_name"],
                            "return_version_id": return_version["version_id"],
                            "product_dataset_name": product_version["dataset_name"],
                            "product_version_id": product_version["version_id"],
                        },
                    }
                )
        return output

    def _raw_source_context(
        self, source_id: str, draft: dict[str, Any], sample_size: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        option = next(
            (item for item in self._raw_source_options() if item["id"] == source_id),
            None,
        )
        if option is None:
            raise ValueError("所选用户反馈数据或产品信息版本已不可用")
        dataset = load_return_dataset_auto(
            Path(option["return"]["file_path"]), Path(option["product"]["file_path"])
        )
        candidates = self._raw_candidates(dataset, draft)
        samples = self._round_robin_samples(
            candidates, sample_size, bucket_fields=("store", "listing")
        )
        if not samples:
            raise ValueError("所选数据中没有当前品类可用于验证的评论")
        config_version_id = self._published_config_id()
        return (
            self._raw_source_details(option, draft, candidates, config_version_id),
            samples,
        )

    @staticmethod
    def _raw_candidates(
        dataset: ReturnDataset, draft: dict[str, Any]
    ) -> list[dict[str, Any]]:
        categories = {
            (str(item["category_a"]), str(item["category_b"]))
            for item in draft["snapshot"]["variants"]
        }
        candidates: list[dict[str, Any]] = []
        for row in dataset.unique_comments.itertuples(index=False):
            category = (str(row.category_a), str(row.category_b))
            if category not in categories or str(row.product_match_status) != "matched":
                continue
            candidates.append(
                {
                    "classification_key": str(row.classification_key),
                    "comment": str(row.comment_normalized),
                    "reason": str(row.reason),
                    "category_a": category[0],
                    "category_b": category[1],
                    "store": str(row.store),
                    "listing": str(row.listing),
                    "record_count": int(cast(SupportsInt, row.record_count)),
                    "baseline": {},
                }
            )
        return candidates

    @staticmethod
    def _raw_source_details(
        option: dict[str, Any],
        draft: dict[str, Any],
        candidates: list[dict[str, Any]],
        config_version_id: str,
    ) -> dict[str, Any]:
        stores = sorted({item["store"] for item in candidates if item["store"]})
        listings = sorted({item["listing"] for item in candidates if item["listing"]})
        public = {
            **option["public"],
            "comparison_mode": "draft_only"
            if draft["is_new"]
            else "baseline_and_draft",
            "unit_count": len(candidates),
            "available_sample_count": len(candidates),
            "store_site": stores[0] if len(stores) == 1 else f"{len(stores)} 个店铺",
            "listing": listings[0]
            if len(listings) == 1
            else f"{len(listings)} 个 Listing",
        }
        return {
            "kind": "raw_dataset",
            "result": public,
            "config_version_id": config_version_id,
            "standard_key": str(draft["standard_key"]),
            "model_policy_version": str(draft["snapshot"]["model_policy"]["version"]),
            "store": stores[0] if len(stores) == 1 else "",
            "listing": listings[0] if len(listings) == 1 else None,
        }

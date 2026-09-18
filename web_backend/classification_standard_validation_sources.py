from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, SupportsInt, cast

from return_semantics.data import load_return_dataset_auto
from return_semantics.prompt import prompt_version, recognition_fingerprint
from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_validation_quality import FACT_QUALITY_POLICY
from web_backend.common import json_value
from web_backend.database import Database


class ClassificationStandardValidationSourcesMixin:
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def _review_source_context(
            self,
            filename: str,
            content: bytes,
            draft: dict[str, Any],
            sample_size: int,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]: ...

    def sources(self, draft_id: str) -> list[dict[str, Any]]:
        draft = self.standard_service.get_draft(draft_id)
        raw_sources = [item["public"] for item in self._raw_source_options()]
        if draft["is_new"]:
            return raw_sources
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.id AS result_version_id, v.version_no,
                       v.quality_status, v.unit_count, v.record_count,
                       v.published_at, r.store_site, r.listing,
                       (
                           SELECT COUNT(*) FROM classification_units unit
                           WHERE unit.result_version_id = v.id
                             AND TRIM(COALESCE(unit.comment, '')) != ''
                             AND unit.quality_status != 'excluded'
                       ) AS available_sample_count
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE r.standard_version_id = ?
                  AND v.publish_status = 'published'
                  AND EXISTS (
                      SELECT 1 FROM classification_units unit
                      WHERE unit.result_version_id = v.id
                        AND TRIM(COALESCE(unit.comment, '')) != ''
                        AND unit.quality_status != 'excluded'
                  )
                ORDER BY v.published_at DESC, v.id DESC
                """,
                (draft["base_version_id"],),
            ).fetchall()
        return [*raw_sources, *(dict(row) for row in rows)]

    def _validation_source_context(
        self,
        draft: dict[str, Any],
        source_result_version_id: str,
        sample_size: int,
        review_file: tuple[str, bytes] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        raw_source_ids = {item["id"] for item in self._raw_source_options()}
        if review_file is not None:
            source, samples = self._review_source_context(
                review_file[0], review_file[1], draft, sample_size
            )
            return source, samples, source["result"]["result_version_id"]
        if source_result_version_id in raw_source_ids:
            source, samples = self._raw_source_context(
                source_result_version_id,
                draft,
                sample_size,
            )
            return source, samples, source_result_version_id
        source = self._source_context(
            source_result_version_id,
            str(draft["base_version_id"]),
        )
        return (
            source,
            self._sample(source_result_version_id, sample_size),
            source_result_version_id,
        )

    def _apply_recognition_context(
        self,
        source: dict[str, Any],
        draft: dict[str, Any],
        draft_id: str,
        expected_revision: int,
        comparison_type: str,
    ) -> None:
        candidate = TaxonomyConfig.model_validate(draft["snapshot"]["taxonomy"])
        baseline = self.standard_service.taxonomy_for_version(
            str(draft["base_version_id"])
        )
        if comparison_type != "standard_version":
            candidate = candidate.model_copy(
                update={
                    "version": f"draft-{draft_id}-r{expected_revision}",
                }
            )
            baseline = candidate.model_copy(
                update={
                    "recognition_profile": "legacy_v3"
                    if comparison_type == "keyword_ab"
                    else "keyword_free_v1",
                }
            )
            candidate = candidate.model_copy(
                update={
                    "recognition_profile": "keyword_free_v1"
                    if comparison_type == "keyword_ab"
                    else "semantic_v1",
                }
            )
        source["comparison_type"] = comparison_type
        source["recognition_contract"] = {
            side: {
                "profile": config.recognition_profile,
                "prompt_version": prompt_version(config),
                "fingerprint": recognition_fingerprint(config),
            }
            for side, config in (("baseline", baseline), ("candidate", candidate))
        }
        source["recognition_taxonomies"] = {
            "baseline": baseline.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
        }
        source["result"].update(
            {
                "comparison_type": comparison_type,
                "recognition_contract": source["recognition_contract"],
            }
        )
        if comparison_type != "standard_version":
            source["result"]["comparison_mode"] = "baseline_and_draft"
        if candidate.recognition_profile == "fact_v2":
            source["quality_policy"] = deepcopy(FACT_QUALITY_POLICY)
            source["result"]["quality_policy"] = source["quality_policy"]

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
        self,
        source_id: str,
        draft: dict[str, Any],
        sample_size: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        option = next(
            (item for item in self._raw_source_options() if item["id"] == source_id),
            None,
        )
        if option is None:
            raise ValueError("所选用户反馈数据或产品信息版本已不可用")
        dataset = load_return_dataset_auto(
            Path(option["return"]["file_path"]),
            Path(option["product"]["file_path"]),
        )
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
        samples = self._round_robin_samples(
            candidates,
            sample_size,
            bucket_fields=("store", "listing"),
        )
        if not samples:
            raise ValueError("所选数据中没有当前品类可用于验证的评论")
        config_version_id = self._published_config_id()
        stores = sorted({item["store"] for item in candidates if item["store"]})
        listings = sorted({item["listing"] for item in candidates if item["listing"]})
        public = {
            **option["public"],
            "comparison_mode": (
                "draft_only" if draft["is_new"] else "baseline_and_draft"
            ),
            "unit_count": len(candidates),
            "available_sample_count": len(candidates),
            "store_site": stores[0] if len(stores) == 1 else f"{len(stores)} 个店铺",
            "listing": (
                listings[0] if len(listings) == 1 else f"{len(listings)} 个 Listing"
            ),
        }
        return (
            {
                "kind": "raw_dataset",
                "result": public,
                "config_version_id": config_version_id,
                "standard_key": str(draft["standard_key"]),
                "model_policy_version": str(
                    draft["snapshot"]["model_policy"]["version"]
                ),
                "store": stores[0] if len(stores) == 1 else "",
                "listing": listings[0] if len(listings) == 1 else None,
            },
            samples,
        )

    def _published_config_id(self) -> str:
        with self.database.connect() as connection:
            config = connection.execute(
                """
                SELECT v.id
                FROM api_connections c
                JOIN api_config_versions v ON v.id = c.active_version_id
                WHERE v.published_at IS NOT NULL
                ORDER BY c.updated_at DESC, v.id
                LIMIT 1
                """
            ).fetchone()
        if config is None:
            raise ValueError("请先验证并发布一个模型服务配置")
        return str(config["id"])

    @staticmethod
    def _round_robin_samples(
        items: list[dict[str, Any]],
        sample_size: int,
        *,
        bucket_fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for item in sorted(items, key=lambda value: value["classification_key"]):
            key = tuple(str(item[field]) for field in bucket_fields)
            buckets.setdefault(key, []).append(item)
        output: list[dict[str, Any]] = []
        keys = sorted(buckets, key=lambda key: (-len(buckets[key]), key))
        while len(output) < sample_size and any(buckets.values()):
            for key in keys:
                if buckets[key] and len(output) < sample_size:
                    output.append(buckets[key].pop(0))
        return output

    def _source_context(
        self,
        result_version_id: str,
        base_version_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                SELECT v.id AS result_version_id, v.version_no,
                       v.quality_status, v.unit_count, v.record_count,
                       v.published_at, r.store_site, r.listing,
                       r.standard_version_id,
                       r.source_task_id, r.source_segment_id
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE v.id = ? AND v.publish_status = 'published'
                """,
                (result_version_id,),
            ).fetchone()
            if result is None:
                raise ValueError("所选分类结果不存在或尚未发布")
            if result["standard_version_id"] != base_version_id:
                raise ValueError("所选分类结果不属于草稿的基础标准版本")
            task = connection.execute(
                """
                SELECT id, config_version_id, store, listing, snapshot_json
                FROM tasks WHERE id = ?
                """,
                (result["source_task_id"],),
            ).fetchone()
            segment = connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (result["source_segment_id"],),
            ).fetchone()
        if task is None or segment is None:
            raise ValueError("分类结果缺少可复用的任务执行上下文")
        public_result = dict(result)
        public_result.pop("source_task_id", None)
        public_result.pop("source_segment_id", None)
        return {
            "result": public_result,
            "task": dict(task),
            "segment": dict(segment),
        }

    def _sample(
        self,
        result_version_id: str,
        sample_size: int,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT unit.classification_key, unit.comment, unit.reason,
                       unit.classification_json, unit.quality_status,
                       MIN(COALESCE(record.category_a, '')) AS category_a,
                       MIN(COALESCE(record.category_b, '')) AS category_b
                FROM classification_units unit
                LEFT JOIN classification_result_records record
                  ON record.result_version_id = unit.result_version_id
                 AND record.classification_key = unit.classification_key
                WHERE unit.result_version_id = ?
                  AND TRIM(COALESCE(unit.comment, '')) != ''
                  AND unit.quality_status != 'excluded'
                GROUP BY unit.classification_key, unit.comment, unit.reason,
                         unit.classification_json, unit.quality_status
                ORDER BY unit.classification_key
                """,
                (result_version_id,),
            ).fetchall()
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            classification = json_value(item.pop("classification_json"), {})
            item["baseline"] = classification
            labels = classification.get("primary_label_codes", [])
            bucket = str(labels[0]) if labels else "__NO_PRIMARY_LABEL__"
            buckets.setdefault(bucket, []).append(item)
        output: list[dict[str, Any]] = []
        keys = sorted(buckets, key=lambda key: (-len(buckets[key]), key))
        while len(output) < sample_size and any(buckets.values()):
            for key in keys:
                if buckets[key] and len(output) < sample_size:
                    output.append(buckets[key].pop(0))
        return output

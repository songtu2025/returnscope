"""集中处理结果记录查询条件和分页校验。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import descendant_label_codes
from web_backend.classification_result_payload import PAGE_SIZE_MAX, QUALITY_STATUSES


class ClassificationResultRecordFiltersMixin:
    if TYPE_CHECKING:

        def taxonomy(self, version_id: str) -> TaxonomyConfig | None: ...

    @staticmethod
    def _records_select() -> str:
        return """
            SELECT r.*, u.processing_status, u.problem_labels_json,
                   u.classification_json
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
        """

    def _record_filters(
        self,
        version_id: str,
        filters: dict[str, str | None],
    ) -> tuple[str, list[Any]]:
        where = ["r.result_version_id = ?"]
        params: list[Any] = [version_id]
        columns = {
            "order_id": "order_id",
            "listing": "listing",
            "source_sku": "source_sku",
            "matched_msku": "matched_msku",
            "product_sku": "product_sku",
            "asin": "asin",
            "product_name": "product_name",
        }
        for name, column in columns.items():
            value = filters.get(name)
            if value:
                where.append(f"r.{column} = ?")
                params.append(value)
        quality_status = filters.get("quality_status")
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("r.quality_status = ?")
            params.append(quality_status)
        problem = filters.get("problem")
        if problem:
            taxonomy = self.taxonomy(version_id)
            codes = descendant_label_codes(taxonomy, problem) if taxonomy else [problem]
            codes = codes or [problem]
            placeholders = ",".join("?" for _ in codes)
            where.append(
                f"""
                EXISTS (
                    SELECT 1 FROM classification_unit_labels f
                    WHERE f.result_version_id = r.result_version_id
                      AND f.classification_key = r.classification_key
                      AND f.label_kind = 'problem' AND f.label_code IN ({placeholders})
                )
                """
            )
            params.extend(codes)
        return " AND ".join(where), params

    @staticmethod
    def _validate_page(page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if not 1 <= page_size <= PAGE_SIZE_MAX:
            raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
        return page, page_size

    @staticmethod
    def _validate_quality_status(value: str) -> None:
        if value not in QUALITY_STATUSES:
            raise ValueError("quality_status 不合法")

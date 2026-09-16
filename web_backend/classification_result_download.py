from __future__ import annotations

import json
from io import BytesIO
from typing import TYPE_CHECKING, Any

import pandas as pd

from return_semantics.schemas import TaxonomyConfig
from web_backend.database import Database


class _ClassificationResultDownload:
    database: Database

    if TYPE_CHECKING:

        def get(self, version_id: str) -> dict[str, Any]: ...

        def taxonomy(self, version_id: str) -> TaxonomyConfig | None: ...

        @staticmethod
        def _records_select() -> str: ...

        @staticmethod
        def _serialize_record(value: dict[str, Any]) -> dict[str, Any]: ...

        @staticmethod
        def _enrich_record(
            value: dict[str, Any],
            taxonomy: TaxonomyConfig | None,
        ) -> dict[str, Any]: ...

    def download(self, version_id: str) -> tuple[bytes, str]:
        version = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._records_select()}
                WHERE r.result_version_id = ?
                ORDER BY r.source_row ASC, r.id ASC
                """,
                (version_id,),
            ).fetchall()
        output = []
        semantics = []
        taxonomy = self.taxonomy(version_id)
        for row in rows:
            item = self._enrich_record(self._serialize_record(dict(row)), taxonomy)
            for unit in item["atomic_facts"]:
                path = unit.get("label_path", [])
                semantics.append(
                    {
                        "source_record_id": item["source_record_id"],
                        "source_row": item["source_row"],
                        "label_code": unit["label_code"],
                        "完整路径": " → ".join(path),
                        "中文事实": unit.get("fact_text_zh") or "",
                        "原文证据": unit.get("original_evidence") or "",
                        "事实编号": unit.get("fact_id") or "",
                        "使用者": unit.get("actor_ref") or "",
                        "商品": unit.get("product_ref") or "",
                        "事件": unit.get("event_ref") or "",
                        "陈述类型": unit.get("statement_type") or "",
                        "操作": unit.get("operation") or "",
                        "条件": unit.get("condition") or "",
                        "确定性": unit.get("certainty") or "AFFIRMED",
                        "因果归属": unit.get("causal_attribution") or "UNKNOWN",
                        "因果说明": unit.get("causal_attribution_reason") or "",
                        "判定理由": unit.get("decision_reason") or "",
                        "证据来源": unit.get("evidence_source") or "UNKNOWN",
                        **{
                            f"第{index}级标签": name
                            for index, name in enumerate(path, 1)
                        },
                        "证据原文": unit.get("evidence", ""),
                        "标准版本": version.get("standard_version_id", ""),
                    }
                )
            output.append(
                {
                    "source_record_id": item["source_record_id"],
                    "source_row": item["source_row"],
                    "return_date": item["return_date"],
                    "order_id": item["order_id"],
                    "store_site": item["store_site"],
                    "listing": item["listing"],
                    "product_name": item["product_name"],
                    "source_sku": item["source_sku"],
                    "matched_msku": item["matched_msku"],
                    "product_sku": item["product_sku"],
                    "asin": item["asin"],
                    "category_a": item["category_a"],
                    "category_b": item["category_b"],
                    "reason": item["reason"],
                    "comment": item["comment"],
                    "product_match_status": item["product_match_status"],
                    "quality_status": item["quality_status"],
                    "processing_status": item["processing_status"],
                    "semantic_disposition": item["semantic_disposition"],
                    "problem_labels": " | ".join(item["problem_labels"]),
                    "classification_json": json.dumps(
                        item["classification"],
                        ensure_ascii=False,
                    ),
                }
            )
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(output).to_excel(
                writer,
                sheet_name="分类结果",
                index=False,
            )
            pd.DataFrame(semantics).to_excel(writer, sheet_name="语义层级", index=False)
        filename = (
            f"classification-{version['listing'] or version['result_id']}"
            f"-v{version['version']}.xlsx"
        )
        return buffer.getvalue(), filename

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import PRODUCT_CATEGORY_COLUMNS, PRODUCT_COLUMNS
from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.dataset_files import PRODUCT_WORKSHEET, DatasetRevisionConflict
from web_backend.settings import Settings


@dataclass
class _ProductWorkbookEdit:
    dataset_id: str
    expected_version: int
    original_name: str
    content_type: str
    workbook: dict[str, pd.DataFrame]
    frame: pd.DataFrame


class DatasetProductWorkbookMixin:
    database: Database
    settings: Settings
    add_version: Callable[..., dict[str, Any]]
    get: Callable[..., dict[str, Any] | None]

    def _current_product_version(
        self,
        dataset_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.file_path,
                       v.original_name, v.content_type
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
        if row is None or row["kind"] != "products":
            raise ValueError("商品维度不存在")
        if int(row["current_version"]) != expected_version:
            raise DatasetRevisionConflict("商品维度已被其他用户修改，请刷新后重试")
        return dict(row)

    @staticmethod
    def _load_product_workbook(
        dataset_id: str,
        expected_version: int,
        source: dict[str, Any],
    ) -> _ProductWorkbookEdit:
        workbook: dict[str, pd.DataFrame] = pd.read_excel(
            Path(str(source["file_path"])),
            sheet_name=None,
            dtype=str,
        )
        frame = workbook.get(PRODUCT_WORKSHEET)
        if frame is None:
            raise ValueError("商品维度缺少“产品信息汇总表”工作表")
        return _ProductWorkbookEdit(
            dataset_id=dataset_id,
            expected_version=expected_version,
            original_name=str(source["original_name"]),
            content_type=str(source["content_type"]),
            workbook=workbook,
            frame=frame,
        )

    def _persist_product_workbook(
        self,
        edit: _ProductWorkbookEdit,
        change_note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        edit.workbook[PRODUCT_WORKSHEET] = edit.frame
        temp_path = self.settings.data_dir / "tmp" / f"{new_id('dimension')}.xlsx"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
                for sheet_name, sheet in edit.workbook.items():
                    sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            return self.add_version(
                dataset_id=edit.dataset_id,
                source_path=temp_path,
                original_name=edit.original_name,
                content_type=edit.content_type,
                change_note=change_note,
                actor_id=actor_id,
                expected_current_version=edit.expected_version,
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _validated_product_row_change(
        frame: pd.DataFrame,
        row_index: int,
        changes: dict[str, str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        if row_index < 0 or row_index >= len(frame):
            raise ValueError("要修改的数据行不存在")
        allowed = {column for column in changes if column in frame.columns}
        if not allowed:
            raise ValueError("没有可修改的字段")
        before = {
            column: ""
            if pd.isna(frame.at[row_index, column])
            else str(frame.at[row_index, column])
            for column in allowed
        }
        normalized = {column: str(changes[column]).strip() for column in allowed}
        changed = {
            column: normalized[column]
            for column in allowed
            if before[column] != normalized[column]
        }
        if not changed:
            raise ValueError("内容没有变化，无需创建新版本")
        return before, changed

    @staticmethod
    def _apply_product_row_change(
        frame: pd.DataFrame,
        row_index: int,
        changes: dict[str, str],
    ) -> None:
        for column in PRODUCT_COLUMNS:
            value = changes.get(column, frame.at[row_index, column])
            if pd.isna(value) or not str(value).strip():
                raise ValueError(f"{column} 不能为空")
        for column, value in changes.items():
            frame.at[row_index, column] = value

    @staticmethod
    def _normalize_category_completion_items(
        store: str | None,
        items: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        fallback_store = (store or "").strip()
        normalized_items: list[dict[str, str]] = []
        seen_products: set[tuple[str, str]] = set()
        for item in items:
            normalized = {
                key: str(item.get(key, "")).strip()
                for key in (
                    "store",
                    "msku",
                    "listing",
                    "category_a",
                    "category_b",
                    "product_name",
                )
            }
            normalized["store"] = normalized["store"] or fallback_store
            if not all(
                normalized[key]
                for key in ("store", "msku", "listing", "category_a", "category_b")
            ):
                raise ValueError("店铺、MSKU、Listing、品类A 和品类B 均不能为空")
            product_key = (normalized["store"], normalized["msku"])
            if product_key in seen_products:
                raise ValueError(
                    f"商品重复提交：{normalized['store']} + {normalized['msku']}"
                )
            seen_products.add(product_key)
            normalized_items.append(normalized)
        return fallback_store, normalized_items

    @staticmethod
    def _product_rows_by_identity(
        frame: pd.DataFrame,
    ) -> dict[tuple[str, str], list[Any]]:
        rows_by_product: dict[tuple[str, str], list[Any]] = {}
        identities = frame[["店铺/站点", "MSKU"]].fillna("").astype(str)
        for index, values in identities.iterrows():
            product_key = (
                str(values["店铺/站点"]).strip(),
                str(values["MSKU"]).strip(),
            )
            rows_by_product.setdefault(product_key, []).append(index)
        return rows_by_product

    @classmethod
    def _apply_category_completion_items(
        cls,
        frame: pd.DataFrame,
        items: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        for column in PRODUCT_CATEGORY_COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        rows_by_product = cls._product_rows_by_identity(frame)
        before_items: list[dict[str, Any]] = []
        for item in items:
            matching = rows_by_product.get((item["store"], item["msku"]), [])
            if matching:
                before_items.append(
                    {
                        "msku": item["msku"],
                        "store": item["store"],
                        "rows": [int(index) for index in matching],
                        "category_a": str(frame.at[matching[0], "品类A"] or ""),
                        "category_b": str(frame.at[matching[0], "品类B"] or ""),
                    }
                )
                for index in matching:
                    frame.at[index, "Listing"] = item["listing"]
                    frame.at[index, "品类A"] = item["category_a"]
                    frame.at[index, "品类B"] = item["category_b"]
                    if "产品名称" in frame.columns and item["product_name"]:
                        frame.at[index, "产品名称"] = item["product_name"]
                continue
            new_row: dict[str, Any] = {column: "" for column in frame.columns}
            new_row.update(
                {
                    "MSKU": item["msku"],
                    "店铺/站点": item["store"],
                    "Listing": item["listing"],
                    "品类A": item["category_a"],
                    "品类B": item["category_b"],
                }
            )
            if "产品名称" in frame.columns:
                new_row["产品名称"] = item["product_name"]
            frame.loc[len(frame), list(new_row)] = list(new_row.values())
            before_items.append(
                {"store": item["store"], "msku": item["msku"], "rows": []}
            )
        return before_items

    def update_product_row(
        self,
        dataset_id: str,
        row_index: int,
        expected_version: int,
        changes: dict[str, str],
        change_note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        source = self._current_product_version(dataset_id, expected_version)
        edit = self._load_product_workbook(
            dataset_id,
            expected_version,
            source,
        )
        before, changed = self._validated_product_row_change(
            edit.frame,
            row_index,
            changes,
        )
        self._apply_product_row_change(edit.frame, row_index, changed)
        result = self._persist_product_workbook(
            edit,
            change_note or f"修改商品维度第 {row_index + 2} 行",
            actor_id,
        )
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "dimension_row_update",
            actor_id,
            before={"row_index": row_index, "values": before},
            after={
                "row_index": row_index,
                "values": changed,
                "note": change_note.strip(),
            },
        )
        return self.get(dataset_id) or result

    def complete_product_categories(
        self,
        dataset_id: str,
        expected_version: int,
        store: str | None,
        items: list[dict[str, str]],
        change_note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        source = self._current_product_version(dataset_id, expected_version)
        fallback_store, normalized_items = self._normalize_category_completion_items(
            store,
            items,
        )
        edit = self._load_product_workbook(
            dataset_id,
            expected_version,
            source,
        )
        before_items = self._apply_category_completion_items(
            edit.frame,
            normalized_items,
        )
        result = self._persist_product_workbook(edit, change_note, actor_id)
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "dimension_category_completion",
            actor_id,
            before={"items": before_items},
            after={
                "store": fallback_store,
                "items": normalized_items,
                "note": change_note.strip(),
            },
        )
        return self.get(dataset_id) or result

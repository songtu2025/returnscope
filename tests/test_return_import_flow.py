from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from return_import_helpers import (
    _create_task_input,
    _database_counts,
    _return_row,
    _write_returns,
)
from test_classification_result_pool import _seed_result_context

from return_semantics.data import (
    RETURN_STORE_COLUMN,
    SOURCE_ORIGIN_COLUMN,
    _prepare_return_records,
)
from web_backend.dataset_service import DatasetService


def _write_returns_xlsx(path: Path, rows: list[dict[str, str]]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"说明": "退货导入文件"}]).to_excel(
            writer,
            sheet_name="说明",
            index=False,
        )
        pd.DataFrame(rows).to_excel(
            writer,
            sheet_name="退货明细",
            index=False,
        )


def test_return_loader_preserves_optional_source_origin_id(tmp_path: Path) -> None:
    source = tmp_path / "returns.csv"
    row = _return_row("ORDER-1", "偏小")
    row[SOURCE_ORIGIN_COLUMN] = "12345"
    _write_returns(source, [row])

    records = _prepare_return_records(source)

    assert records.loc[0, SOURCE_ORIGIN_COLUMN] == "12345"


def test_return_import_recognizes_identity_and_separates_task_input(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "senwayzon-us.csv"
    _write_returns(
        source,
        [_return_row("O-1", "偏小"), _return_row("O-2", "不够保暖")],
    )

    inspection = service.inspect_return_import(source, source.name)
    assert inspection["source_key"] == "SENWAYZON:US"
    assert inspection["suggested_name"] == "SENWAYZON US 用户反馈数据"
    assert "matches" not in inspection

    one_off = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    assert one_off["dataset"]["usage_scope"] == "task_input"
    assert one_off["dataset"]["source_name"] == "SENWAYZON US 用户反馈数据"
    assert not service.list("returns", "managed")
    assert one_off["dataset"]["id"] not in {
        item["id"] for item in service.list("returns", "managed")
    }

    repeated = service.inspect_return_import(source, source.name)
    assert repeated["duplicate"]["version_id"] == one_off["version_id"]


def test_return_xlsx_import_uses_matching_sheet(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "senwayzon-us.xlsx"
    _write_returns_xlsx(source, [_return_row("O-1", "偏小")])

    inspection = service.inspect_return_import(source, source.name)
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        mode="analyze_only",
        actor_id="user-1",
        _inspection=inspection,
    )
    preview = service.preview_rows(str(result["dataset"]["id"]))

    assert inspection["row_count"] == 1
    assert inspection["stores"] == ["SENWAYZON:US"]
    assert preview["records"][0]["order-id"] == "O-1"
    assert service.version_file(str(result["dataset"]["id"]))["original_name"] == (
        source.name
    )


def test_return_import_does_not_fill_missing_store(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "missing-store.csv"
    row = _return_row("O-1", "偏小")
    row[RETURN_STORE_COLUMN] = ""
    _write_returns(source, [row])

    inspection = service.inspect_return_import(source, source.name)

    assert inspection["stores"] == []
    assert inspection["source_key"] == ""
    assert inspection["quality"]["missing_store_rows"] == 1
    before = service.list("returns")
    with pytest.raises(ValueError, match="缺少店铺/站点"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
        )
    assert service.list("returns") == before


@pytest.mark.parametrize("mode", ["create", "append", "replace"])
def test_retired_import_modes_cannot_write(tmp_path: Path, mode: str) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    before = _database_counts(context.database)
    with pytest.raises(ValueError, match="长期数据源导入已下线"):
        service.import_returns(
            source_path=tmp_path / "unused.csv",
            original_name="unused.csv",
            content_type="text/csv",
            mode=mode,
            actor_id="user-1",
        )
    assert _database_counts(context.database) == before


def test_same_file_never_reuses_managed_source(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "managed.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    old = _create_task_input(service, source)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE datasets SET usage_scope = 'managed' WHERE id = ?", (old["id"],)
        )
    inspection = service.inspect_return_import(source, source.name)
    assert inspection["duplicate"] is None
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=inspection,
    )
    assert result["dataset"]["id"] != old["id"]
    assert result["dataset"]["usage_scope"] == "task_input"
    assert result["duplicate"] is False


def test_transaction_rechecks_lifecycle_after_inspection(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "changed-scope.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    old = _create_task_input(service, source)
    stale = service.inspect_return_import(source, source.name)
    assert stale["duplicate"] is not None
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE datasets SET usage_scope = 'managed' WHERE id = ?", (old["id"],)
        )
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=stale,
    )
    assert result["dataset"]["id"] != old["id"]


def test_concurrent_task_uploads_deduplicate_inside_transaction(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "parallel.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    inspection = service.inspect_return_import(source, source.name)

    def upload():
        return service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
            _inspection=inspection,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(), range(2)))
    assert len({result["version_id"] for result in results}) == 1
    assert sum(result["duplicate"] for result in results) == 1

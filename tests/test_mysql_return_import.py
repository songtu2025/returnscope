from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mysql_return_helpers import source as source
from test_return_import_flow import _return_row

from return_semantics.data import RETURN_STORE_COLUMN, SOURCE_ORIGIN_COLUMN
from web_backend import dataset_service as dataset_module
from web_backend.mysql_return_service import FIELD_LABELS


def test_preview_reports_over_limit_without_creating_dataset(source):
    service, cursor, _, payload = source
    columns = cursor.fetchall.return_value
    cursor.fetchall.side_effect = [columns, [_return_row("O-1", "偏小")]]
    cursor.fetchone.return_value = {"total": 3}
    before = len(service.datasets.list("returns"))
    preview = service.preview(payload)
    assert preview["over_limit"] is True
    assert preview["row_count"] == 3
    assert len(preview["rows"]) == 1
    assert len(service.datasets.list("returns")) == before


def test_import_freezes_data_reuses_duplicates_and_records_source(source, monkeypatch):
    service, cursor, _, payload = source
    inspect = MagicMock(wraps=dataset_module.inspect_file)
    monkeypatch.setattr(dataset_module, "inspect_file", inspect)
    rows = [_return_row("MYSQL-1", "数据库评论，偏小")]
    cursor.__iter__.side_effect = lambda: iter(rows)
    result = service.import_returns(payload, "user-1")
    assert inspect.call_count == 1
    assert result["dataset"]["usage_scope"] == "task_input"
    version = service.datasets.version_file(result["dataset"]["id"])
    snapshot = Path(version["file_path"])
    assert "数据库评论，偏小" in snapshot.read_text(encoding="utf-8-sig")
    repeated = service.import_returns(payload, "user-1")
    assert repeated["duplicate"] is True
    assert repeated["version_id"] == result["version_id"]
    rows[0]["customer-comments"] = "源数据后来改变"
    assert "源数据后来改变" not in snapshot.read_text(encoding="utf-8-sig")
    with service.datasets.database.connect() as connection:
        audit = connection.execute(
            "SELECT after_json FROM audit_logs WHERE action = 'import_mysql_returns'"
        ).fetchall()
    assert len(audit) == 2
    assert "sale_return_order" in audit[0]["after_json"]
    assert service.settings.mysql_password not in audit[0]["after_json"]
    assert not list((service.settings.data_dir / "tmp").glob("mysql_*.csv"))


def test_mysql_import_keeps_source_id_in_snapshot(source):
    service, cursor, _, payload = source
    cursor.fetchall.return_value = [
        {"name": key.replace("-", "_"), "type": "varchar"} for key in FIELD_LABELS
    ] + [{"name": "id", "type": "bigint"}]
    row = _return_row("O-1", "偏小")
    row[SOURCE_ORIGIN_COLUMN] = "12345"
    cursor.__iter__.side_effect = lambda: iter([row])

    result = service.import_returns(payload, "user-1")
    version = service.datasets.version_file(result["dataset"]["id"])
    snapshot = Path(version["file_path"]).read_text(encoding="utf-8-sig")
    assert SOURCE_ORIGIN_COLUMN in snapshot.splitlines()[0]
    assert "12345" in snapshot


@pytest.mark.parametrize("problem", ["empty", "too_many", "empty_store"])
def test_failed_import_cleans_temporary_file_and_creates_no_dataset(source, problem):
    service, cursor, _, payload = source
    rows = [_return_row("MYSQL-1", "偏小")]
    if problem == "empty":
        rows = []
    elif problem == "too_many":
        rows *= 3
    else:
        rows[0][RETURN_STORE_COLUMN] = ""
    cursor.__iter__.return_value = iter(rows)
    before = len(service.datasets.list("returns"))
    with pytest.raises(ValueError):
        service.import_returns(payload, "user-1")
    assert len(service.datasets.list("returns")) == before
    assert not list((service.settings.data_dir / "tmp").glob("mysql_*.csv"))

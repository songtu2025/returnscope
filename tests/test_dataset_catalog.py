from pathlib import Path
from types import SimpleNamespace

import pytest
from test_classification_result_pool import _seed_result_context

from web_backend.common import add_audit
from web_backend.dataset_service import DatasetService


@pytest.fixture
def catalog_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context = _seed_result_context(tmp_path)
    add_audit(context.database, "dataset", "dataset-returns", "inspect", "user-1")
    with context.database.transaction() as connection:
        for import_id in ["import-1", "import-2"]:
            connection.execute(
                """
                INSERT INTO dataset_imports(
                    id, dataset_id, resulting_version_id, mode,
                    raw_file_path, original_name, content_type, size_bytes,
                    raw_sha256, row_count, column_count, schema_json,
                    quality_json, created_by, created_at
                ) VALUES (?, 'dataset-returns', 'version-returns', 'create',
                          'synthetic.csv', 'synthetic.csv', 'text/csv', 1,
                          'synthetic-sha', 3, 10, '[]', '{}', 'user-1',
                          '2026-08-12T00:00:00+00:00')
                """,
                (import_id,),
            )
    queries = []
    original_connect = context.database.connect

    def connect():
        connection = original_connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(context.database, "connect", connect)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    return service, queries


@pytest.mark.parametrize(
    "include,expected_fields,query_count",
    [
        (None, {"versions", "imports", "audit"}, 4),
        (set(), set(), 1),
        ({"unknown"}, set(), 1),
        ({"versions"}, {"versions"}, 2),
        ({"imports"}, {"imports"}, 2),
        ({"audit"}, {"audit"}, 2),
    ],
)
def test_dataset_details_include_only_requested_history(
    catalog_context, include, expected_fields, query_count
) -> None:
    service, queries = catalog_context

    item = service.get("dataset-returns", include)

    assert item is not None
    assert item.keys() & {"versions", "imports", "audit"} == expected_fields
    assert item["task_reference_count"] == 1
    assert item["source_name"] == "退货数据"
    assert len(queries) == query_count
    if "versions" in expected_fields:
        assert [version["version"] for version in item["versions"]] == [1]
        assert "file_path" not in item["versions"][0]
    if "imports" in expected_fields:
        assert [entry["id"] for entry in item["imports"]] == ["import-2", "import-1"]
        assert all("raw_file_path" not in entry for entry in item["imports"])
    if "audit" in expected_fields:
        assert len(item["audit"]) == 1


def test_missing_dataset_does_not_query_history(catalog_context) -> None:
    service, queries = catalog_context

    assert service.get("absent") is None
    assert len(queries) == 1

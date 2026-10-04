from pathlib import Path

import pytest
from test_dashboard_versions import _create_dashboard, _ready_result


def _review_bias_fixture(tmp_path: Path, total: int, pending: int):
    context, version, service = _ready_result(tmp_path)
    source_id = str(version["version_id"])
    _, dashboard = _create_dashboard(service, source_id)
    with context.database.transaction() as connection:
        original = dict(
            connection.execute(
                "SELECT * FROM classification_result_records "
                "WHERE result_version_id = ? ORDER BY id LIMIT 1",
                (source_id,),
            ).fetchone()
        )
        columns = ", ".join(original)
        placeholders = ", ".join("?" for _ in original)
        for index in range(total + 20):
            record = {
                **original,
                "id": f"bias-record-{index}",
                "source_record_id": f"bias-source-{index}",
                "order_id": f"bias-order-{index}",
                "source_row": index + 100,
                "product_name": "集中商品" if index < total else "其他商品",
                "quality_status": "review_required" if index < pending else "ready",
            }
            connection.execute(
                f"INSERT INTO classification_result_records ({columns}) "
                f"VALUES ({placeholders})",
                tuple(record.values()),
            )
    return service, str(dashboard["id"]), str(dashboard["version"]["version_id"])


@pytest.mark.parametrize(
    ("total", "pending", "detected"),
    [(9, 4, False), (9, 5, False), (10, 4, False), (10, 5, True)],
)
def test_review_bias_requires_product_sample_and_pending_thresholds(
    tmp_path: Path, total: int, pending: int, detected: bool
) -> None:
    service, dashboard_id, version_id = _review_bias_fixture(tmp_path, total, pending)
    result = service.review_bias(dashboard_id, version_id)
    assert result["status"] == ("concentrated" if detected else "not_detected")
    assert result["pending_record_count"] == pending
    if detected:
        assert result["concentrated_products"] == [
            {
                "value": "集中商品",
                "total_record_count": 10,
                "pending_record_count": 5,
                "pending_rate": 50.0,
                "difference_percentage_points": round(50.0 - result["pending_rate"], 2),
            }
        ]
    else:
        assert result["concentrated_products"] == []


def test_review_bias_skips_product_query_without_pending_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, dashboard_id, version_id = _review_bias_fixture(tmp_path, 10, 0)
    original_connect = service.database.connect
    queries = []

    def connect():
        connection = original_connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(service.database, "connect", connect)
    result = service.review_bias(dashboard_id, version_id)
    assert result["status"] == "not_applicable"
    assert result["pending_record_count"] == 0
    assert not any("HAVING COUNT(*) >= 10" in query for query in queries)

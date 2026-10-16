import logging
import re
from collections import OrderedDict
from pathlib import Path

import pandas as pd
from test_task_plan_selection import _service

from web_backend import dataset_cache


def test_plan_stage_timings_keep_results_and_log_only_metrics(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())

    def reject_unused_catalog_read(*args, **kwargs):
        raise AssertionError("没有待处理商品时不应再次读取完整产品资料")

    monkeypatch.setattr(
        "web_backend.task_plan_service.load_product_frame", reject_unused_catalog_read
    )
    with caplog.at_level(logging.INFO, logger="uvicorn.error.performance"):
        cold = service.preflight(
            "version-returns", "version-products", None, None, "config-1"
        )
        warm = service.preflight(
            "version-returns", "version-products", None, None, "config-1"
        )
    assert cold == warm
    messages = [record.getMessage() for record in caplog.records]
    dataset_logs = [text for text in messages if text.startswith("dataset_auto ")]
    cache_logs = [text for text in messages if text.startswith("dataset_cache ")]
    plan_logs = [text for text in messages if text.startswith("plan_prepare ")]
    assert len(dataset_logs) == 1
    assert len(plan_logs) == len(cache_logs) == 2
    assert "hit=False" in cache_logs[0]
    assert "hit=True" in cache_logs[1]
    for field in ("products_ms", "feedback_ms", "matching_ms", "grouping_ms"):
        assert re.search(rf"{field}=\d+\.\d+", dataset_logs[0])
    for field in (
        "inputs_ms",
        "dataset_ms",
        "plan_ms",
        "resolution_ms",
        "response_ms",
        "total_ms",
    ):
        assert re.search(rf"{field}=\d+\.\d+", plan_logs[0])
    text = "\n".join(messages)
    assert str(tmp_path) not in text
    assert "version-returns" not in text
    assert "SEEKWAY" not in text
    assert "SKU-1" not in text
    for comment in pd.read_csv(tmp_path / "returns.csv")["customer-comments"]:
        assert comment not in text

import json
import tracemalloc
from pathlib import Path

import pytest

from return_semantics.model_cache import JsonlCache
from return_semantics.model_results import ModelCallResult
from return_semantics.schemas import ModelClassification


def test_streaming_load_preserves_last_value_and_never_reads_whole_file(
    tmp_path, monkeypatch
):
    path = tmp_path / "cache.jsonl"
    cache = JsonlCache(path)
    result = ModelCallResult(ModelClassification(), "初次模型", {}, {})
    cache.put("key", result)
    cache.put("key", ModelCallResult(result.classification, "重试模型", {}, {}))
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n \n")

    def no_full_read(*args, **kwargs):
        raise AssertionError("缓存加载不应读取整个文件字符串")

    monkeypatch.setattr(Path, "read_text", no_full_read)
    restored = JsonlCache(path)
    assert restored.get("key").model_name == "重试模型"
    assert restored.get("key").classification == result.classification
    assert restored.get("missing") is None
    assert restored.lock_for("key") is restored.lock_for("key")


def test_streaming_load_avoids_file_sized_temporary_buffers(tmp_path):
    path = tmp_path / "cache.jsonl"
    record = json.dumps(
        {
            "cache_key": "same-key",
            "model_name": "合成模型",
            "classification": ModelClassification().model_dump(mode="json"),
            "metrics": {"sample": "x" * 500},
        },
        ensure_ascii=False,
    )
    path.write_text((record + "\n") * 5000, encoding="utf-8")
    tracemalloc.start()
    try:
        cache = JsonlCache(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert cache.get("same-key") is not None
    assert peak < path.stat().st_size // 5


def test_complete_corrupted_cache_record_still_fails(tmp_path):
    path = tmp_path / "cache.jsonl"
    path.write_text("{invalid}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        JsonlCache(path)

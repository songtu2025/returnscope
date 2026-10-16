import json

import pytest

from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from web_backend.task_execution.checkpoints import (
    append_checkpoint,
    load_checkpoint,
    write_checkpoint,
)


@pytest.fixture
def result():
    return ValidatedClassification(
        classification_key="合成评论",
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="合成模型",
        prompt_version="v1",
        taxonomy_version="v1",
    )


def test_legacy_snapshot_append_override_and_compaction(tmp_path, result):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"old": result.model_dump(mode="json")}, indent=2),
        encoding="utf-8",
    )
    updated = result.model_copy(update={"model_name": "重试模型"})
    append_checkpoint(path, {"new": result, "old": updated})
    assert load_checkpoint(path) == {"old": updated, "new": result}
    write_checkpoint(path, load_checkpoint(path))
    assert (
        json.loads(path.read_text(encoding="utf-8"))["old"]["model_name"] == "重试模型"
    )
    assert load_checkpoint(path) == {"old": updated, "new": result}


def test_torn_last_record_recovers_completed_records(tmp_path, result):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, {"old": result})
    append_checkpoint(path, {"new": result})
    with path.open("a", encoding="utf-8") as output:
        output.write('{"unfinished":')
    assert load_checkpoint(path) == {"old": result, "new": result}
    write_checkpoint(path, load_checkpoint(path))
    append_checkpoint(path, {"resumed": result})
    assert set(load_checkpoint(path)) == {"old", "new", "resumed"}


def test_torn_utf8_tail_keeps_saved_records(tmp_path, result):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, {"old": result})
    with path.open("ab") as output:
        output.write(b'\n{"tail":"' + "中文".encode("utf-8")[:-1])
    assert load_checkpoint(path) == {"old": result}


@pytest.mark.parametrize("text", ["{invalid", "{}\n{invalid\n{}", "{}\n{invalid\n"])
def test_corrupted_complete_record_is_not_hidden(tmp_path, text):
    path = tmp_path / "checkpoint.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_checkpoint(path)


def test_append_volume_is_linear_and_results_match(tmp_path, result):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, {})
    expected = {}
    for start in range(0, 1000, 5):
        delta = {str(i): result for i in range(start, start + 5)}
        expected.update(delta)
        append_checkpoint(path, delta)
    assert load_checkpoint(path) == expected
    serialized = json.dumps(
        {key: value.model_dump(mode="json") for key, value in expected.items()},
        ensure_ascii=False,
    ).encode("utf-8")
    assert path.stat().st_size < len(serialized) * 1.02
    write_checkpoint(path, expected)
    assert path.read_bytes() == serialized

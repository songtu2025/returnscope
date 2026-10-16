"""检查点执行时追加增量，暂停或完成时原子合并为完整快照。"""

from __future__ import annotations

import json
from codecs import getincrementaldecoder
from pathlib import Path

from return_semantics.schemas import ValidatedClassification


def load_checkpoint(path: Path) -> dict[str, ValidatedClassification]:
    if not path.exists():
        return {}
    text = getincrementaldecoder("utf-8")().decode(path.read_bytes(), final=False)
    decoder = json.JSONDecoder()
    data: dict[str, object] = {}
    position = 0
    documents = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        try:
            delta, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            # 只容忍异常退出留下的最后一条未写完记录，完整坏记录仍报错。
            if documents and "\n" not in text[position:]:
                break
            raise
        data.update(delta)
        documents += 1
    return {
        str(key): ValidatedClassification.model_validate(value)
        for key, value in data.items()
    }


def _serialize(results: dict[str, ValidatedClassification]) -> str:
    return json.dumps(
        {key: value.model_dump(mode="json") for key, value in results.items()},
        ensure_ascii=False,
    )


def write_checkpoint(path: Path, results: dict[str, ValidatedClassification]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(_serialize(results), encoding="utf-8")
    temporary.replace(path)


def append_checkpoint(path: Path, results: dict[str, ValidatedClassification]) -> None:
    if results:
        with path.open("a", encoding="utf-8") as output:
            output.write("\n" + _serialize(results) + "\n")

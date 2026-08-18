import pandas as pd

from return_semantics.sampling import (
    build_gold_sample,
    classify_sample_bucket,
)


def test_sample_bucket_classification() -> None:
    assert classify_sample_bucket("Too Small|Length too short|No") == "问卷式评论"
    assert classify_sample_bucket("Too small") == "短评论"
    assert (
        classify_sample_bucket("I need a smaller size for this shoe") == "语义风险评论"
    )


def test_gold_sample_has_stable_size_and_split() -> None:
    comments = pd.DataFrame(
        [
            {
                "classification_key": f"reason-{index}\x1fcomment-{index}",
                "reason": f"REASON_{index % 4}",
                "comment_normalized": f"Comment number {index} but different",
                "record_count": index + 1,
            }
            for index in range(100)
        ]
    )

    sample = build_gold_sample(
        comments,
        total=20,
        calibration_size=12,
        seed=7,
    )

    assert len(sample) == 20
    assert sample["样本编号"].is_unique
    assert sample["数据用途"].value_counts().to_dict() == {
        "提示校准": 12,
        "不可见验收": 8,
    }
    assert "classification_key" not in sample.columns

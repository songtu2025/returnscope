from collections import Counter

from test_insight_reports import _complete_report, _service_context

from web_backend.insight_report_contracts import V10_PROMPT_VERSION
from web_backend.insight_reports.v8_statistics import _Topic
from web_backend.insight_reports.v8_text_signals import EARLY_FAILURE
from web_backend.insight_reports.v10_content import assemble_verifiable
from web_backend.insight_reports.v10_evidence import build_verifiable_report


def test_verifiable_report_keeps_direction_and_denominators_separate():
    quality = _Topic(count=249, negative=200, text_signals=Counter({EARLY_FAILURE: 85}))
    quality.negative_months.update(
        dict(
            zip(
                ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08"),
                (5, 15, 41, 42, 35),
                strict=True,
            )
        )
    )
    sizing = _Topic(opposed_pairs=Counter(left=95, right=61, overlap=5))
    stats = {
        "overview": {"total": 909, "mapped": 712},
        "topics": {"质量与耐用": quality, "尺码与适配": sizing},
        "months": dict(
            zip(
                ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08"),
                (59, 91, 152, 160, 121),
                strict=True,
            )
        ),
        "locations": {},
        "examples": {},
    }
    evidence = build_verifiable_report(
        {
            "source": {"pending_review_record_count": 223},
            "blueprint": {"boundaries": []},
        },
        stats,
    )
    result = assemble_verifiable(
        evidence,
        {
            "chapters": [
                {
                    "id": "durability",
                    "explanation": "故障达到 999 条，模型覆盖指标。",
                    "evidence_ids": ["durability"],
                }
            ]
        },
    )
    chapters = {item.id: item for item in result.chapters}
    durability = chapters["durability"]
    assert [(item.numerator, item.denominator) for item in durability.metrics] == [
        (249, 909),
        (200, 909),
        (85, 200),
    ]
    assert durability.metrics[-1].percent == 42.5
    assert "999" not in durability.explanation
    fit = chapters["fit"]
    assert fit.metrics[0].numerator == 95 + 61 - 5 == 151
    assert [row.numerator for row in fit.breakdown[:3]] == [90, 5, 56]
    assert [(m.numerator, m.denominator) for m in chapters["signals"].metrics] == [
        (20, 150),
        (118, 433),
        (35, 121),
    ]
    assert sum(m.numerator for m in chapters["coverage"].metrics) == 909


def test_current_report_uses_verifiable_contract(tmp_path):
    _, dashboard, service, _ = _service_context(tmp_path, client_payload={})
    report = _complete_report(dashboard, service)
    assert report["status"] == "completed", report
    assert report["prompt_version"] == V10_PROMPT_VERSION
    assert report["content"]["report_type"] == "verifiable_insight"
    assert len(report["content"]["chapters"]) == 6

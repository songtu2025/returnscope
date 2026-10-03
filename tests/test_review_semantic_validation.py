import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from test_result_version_reviews import _publish_review_required

from web_backend.database import Database
from web_backend.review_batch_editing import ReviewBatchEditingMixin
from web_backend.review_batches import record_editing as editing_module
from web_backend.review_batches import semantic_validation as validation_module
from web_backend.review_service import ReviewService

NOW = "2026-10-01T00:00:00+00:00"


def _validation_context() -> SimpleNamespace:
    editor = ReviewBatchEditingMixin()
    editor.standard_service = Mock()
    editor.standard_service.taxonomy_config_for_result_version.return_value = (
        SimpleNamespace(labels=[SimpleNamespace(code="VALID")])
    )
    return SimpleNamespace(
        editor=editor,
        connection=Mock(),
        row={
            "id": "review-1",
            "batch_id": "batch-1",
            "revision": 1,
            "workflow_status": "pending",
            "comment": "ALPHA (test)\n beta",
            "classification_json": json.dumps(
                {"semantic_units": [], "semantic_review": {"cached": True}},
            ),
        },
        view=Mock(
            return_value={
                "semantic_items": [
                    {"item_id": "item-1", "business_review_required": True},
                    {"item_id": "diagnostic-1", "business_review_required": False},
                ],
                "unexplained_fragments": ["beta"],
            }
        ),
    )


def _run_update(
    context: SimpleNamespace, details: dict[str, Any], **overrides: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    arguments = {
        "result_version_id": "version-1",
        "expected_revision": 1,
        "actor_id": "user-1",
        "action": "exclude",
        "label_code": None,
        "note": "核验",
        "now": NOW,
        **details,
        **overrides,
    }
    return context.editor._update_batch_record_row(
        context.connection, context.row, **arguments
    )


@pytest.fixture
def validation_context(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    context = _validation_context()
    monkeypatch.setattr(validation_module, "build_semantic_review_view", context.view)
    monkeypatch.setattr(editing_module, "new_id", lambda _prefix: "revision-fixed")
    return context


ACCEPTED_DETAILS = [
    {},
    {
        "semantic_item_reviews": None,
        "added_semantic_items": None,
        "coverage_status": None,
    },
    {"semantic_item_reviews": []},
    {"added_semantic_items": []},
    {"semantic_item_reviews": [], "added_semantic_items": []},
    {"coverage_status": "complete"},
    {"coverage_status": "has_omission"},
    {
        "semantic_item_reviews": [
            {
                "semantic_item_id": "item-1",
                "action": "change_label",
                "label_code": "VALID",
            }
        ]
    },
    {
        "semantic_item_reviews": [
            {"semantic_item_id": "item-1", "action": "remove", "label_code": "MISSING"}
        ]
    },
    {
        "semantic_item_reviews": [
            {"semantic_item_id": "item-1", "action": "no_tag_needed"}
        ]
    },
    {
        "semantic_item_reviews": [
            {
                "semantic_item_id": "unexplained-0",
                "action": "change_label",
                "label_code": "VALID",
            }
        ]
    },
    {
        "semantic_item_reviews": [
            {
                "semantic_item_id": " item-1 ",
                "action": " change_label ",
                "label_code": " VALID ",
            }
        ]
    },
    {
        "semantic_item_reviews": [
            {"semantic_item_id": "item-1", "action": "remove"},
            {"semantic_item_id": "item-1", "action": "no_tag_needed"},
        ]
    },
    {
        "added_semantic_items": [
            {"label_code": " VALID ", "evidence_text": " alpha (test)   beta "}
        ]
    },
    {
        "semantic_item_reviews": [{"semantic_item_id": "item-1", "action": "remove"}],
        "added_semantic_items": [
            {"label_code": "VALID", "evidence_text": "alpha"},
            {"label_code": "VALID", "evidence_text": "beta"},
        ],
        "coverage_status": "has_omission",
    },
]


@pytest.mark.parametrize("details", ACCEPTED_DETAILS)
def test_valid_details_preserve_input_and_saved_order(
    validation_context: SimpleNamespace, details: dict[str, Any]
) -> None:
    payload = copy.deepcopy(details)
    original_row = copy.deepcopy(validation_context.row)
    before, after = _run_update(validation_context, payload)

    assert payload == details
    assert validation_context.row == original_row
    assert before == json.loads(original_row["classification_json"])
    calls = validation_context.connection.execute.call_args_list
    assert len(calls) == 2
    assert calls[0].args[1][:3] == ("excluded", editing_module.json_text(after), 2)
    assert calls[1].args[1][3:5] == (
        editing_module.json_text(before),
        editing_module.json_text(after),
    )
    expected_lookups = int(any(value is not None for value in details.values()))
    assert validation_context.view.call_count == expected_lookups
    for field, saved_key in [
        ("semantic_item_reviews", "human_semantic_reviews"),
        ("added_semantic_items", "human_added_semantic_items"),
    ]:
        if details.get(field) is not None:
            assert after[saved_key] == [
                {**item, "assessed_by": "user-1", "assessed_at": NOW}
                for item in details[field]
            ]


REJECTED_DETAILS = [
    ({"coverage_status": ""}, "语义覆盖状态不合法"),
    (
        {
            "coverage_status": "COMPLETE",
            "semantic_item_reviews": [{"semantic_item_id": "missing"}],
        },
        "语义覆盖状态不合法",
    ),
    (
        {
            "semantic_item_reviews": [
                {
                    "semantic_item_id": "missing",
                    "action": "invalid",
                    "label_code": "MISSING",
                }
            ]
        },
        "选择的语义核验项不存在",
    ),
    (
        {
            "semantic_item_reviews": [
                {"semantic_item_id": "diagnostic-1", "action": "invalid"}
            ]
        },
        "系统诊断项不能由业务复核修改",
    ),
    (
        {
            "semantic_item_reviews": [
                {
                    "semantic_item_id": "item-1",
                    "action": "invalid",
                    "label_code": "MISSING",
                }
            ]
        },
        "语义核验处理动作不合法",
    ),
    (
        {
            "semantic_item_reviews": [
                {"semantic_item_id": "item-1", "action": "change_label"}
            ]
        },
        "选择的语义标签不存在",
    ),
    (
        {
            "semantic_item_reviews": [
                {
                    "semantic_item_id": "item-1",
                    "action": "change_label",
                    "label_code": "MISSING",
                }
            ]
        },
        "选择的语义标签不存在",
    ),
    (
        {
            "semantic_item_reviews": [
                {"semantic_item_id": "unexplained-1", "action": "remove"}
            ]
        },
        "选择的语义核验项不存在",
    ),
    (
        {
            "added_semantic_items": [
                {"label_code": "MISSING", "evidence_text": "foreign"}
            ]
        },
        "选择的语义标签不存在",
    ),
    (
        {"added_semantic_items": [{"label_code": "VALID", "evidence_text": " "}]},
        "人工补充项的证据必须来自当前用户反馈",
    ),
    (
        {"added_semantic_items": [{"label_code": "VALID", "evidence_text": "foreign"}]},
        "人工补充项的证据必须来自当前用户反馈",
    ),
    (
        {
            "added_semantic_items": [
                {"label_code": "VALID", "evidence_text": "alpha.*beta"}
            ]
        },
        "人工补充项的证据必须来自当前用户反馈",
    ),
    (
        {
            "semantic_item_reviews": [
                {"semantic_item_id": "item-1", "action": "remove"},
                {"semantic_item_id": "missing", "action": "remove"},
            ],
            "added_semantic_items": [{"label_code": "MISSING"}],
        },
        "选择的语义核验项不存在",
    ),
    (
        {
            "added_semantic_items": [
                {"label_code": "VALID", "evidence_text": "alpha"},
                {"label_code": "VALID", "evidence_text": "foreign"},
            ]
        },
        "人工补充项的证据必须来自当前用户反馈",
    ),
]


@pytest.mark.parametrize("details,message", REJECTED_DETAILS)
def test_invalid_details_preserve_first_error_and_never_write(
    validation_context: SimpleNamespace, details: dict[str, Any], message: str
) -> None:
    payload = copy.deepcopy(details)
    original_row = copy.deepcopy(validation_context.row)
    with pytest.raises(ValueError) as caught:
        _run_update(validation_context, payload)

    assert str(caught.value) == message
    assert payload == details
    assert validation_context.row == original_row
    validation_context.connection.execute.assert_not_called()
    if message == "语义覆盖状态不合法":
        validation_context.editor.standard_service.taxonomy_config_for_result_version.assert_not_called()
        validation_context.view.assert_not_called()


@pytest.mark.parametrize(
    "overrides,row_changes,message",
    [
        ({"action": "invalid"}, {}, "复核处理动作不合法"),
        ({"action": "modify", "label_code": " "}, {}, "修改分类时请选择目标标签"),
        ({"expected_revision": 0}, {}, "记录已被其他用户修改，请刷新后重试"),
        ({}, {"workflow_status": "resolved"}, "只能处理待处理的复核记录"),
    ],
)
def test_record_guards_precede_semantic_coverage_validation(
    validation_context: SimpleNamespace,
    overrides: dict[str, Any],
    row_changes: dict[str, Any],
    message: str,
) -> None:
    validation_context.row.update(row_changes)
    with pytest.raises(ValueError) as caught:
        _run_update(validation_context, {"coverage_status": "invalid"}, **overrides)
    assert str(caught.value) == message
    validation_context.view.assert_not_called()
    validation_context.connection.execute.assert_not_called()


@pytest.fixture
def saved_review(tmp_path: Path) -> SimpleNamespace:
    context, base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    batch = service.create_batch(str(base["version_id"]), "user-1", "验证核验行为")
    review = service.batch_records(batch["id"])["items"][0]
    return SimpleNamespace(
        database=context.database, service=service, batch=batch, review=review
    )


def _database_state(database: Database) -> dict[str, list[tuple[Any, ...]]]:
    with database.connect() as connection:
        return {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")
            ]
            for table in (
                "review_records",
                "review_batches",
                "review_revisions",
                "task_events",
                "audit_logs",
            )
        }


@pytest.mark.parametrize("action", ["confirm", "modify", "exclude"])
def test_valid_details_persist_for_each_record_action(
    saved_review: SimpleNamespace, action: str
) -> None:
    record = saved_review.review
    item = record["classification"]["semantic_review"]["semantic_items"][0]
    reviews = [{"semantic_item_id": item["item_id"], "action": "remove"}]
    added = [
        {"label_code": item["label_code"], "evidence_text": record["comment"].upper()}
    ]
    updated = saved_review.service.update_batch_record(
        saved_review.batch["id"],
        record["id"],
        record["revision"],
        "user-1",
        item["label_code"] if action == "modify" else None,
        "保存核验详情",
        action=action,
        semantic_item_reviews=reviews,
        added_semantic_items=added,
        coverage_status="complete",
    )

    assert updated["revision"] == record["revision"] + 1
    assert updated["workflow_status"] == (
        "excluded" if action == "exclude" else "resolved"
    )
    assert (
        updated["classification"]["human_semantic_reviews"][0]["semantic_item_id"]
        == item["item_id"]
    )
    assert (
        updated["classification"]["human_added_semantic_items"][0]["evidence_text"]
        == added[0]["evidence_text"]
    )
    assert updated["classification"]["coverage_review"]["status"] == "complete"
    state = _database_state(saved_review.database)
    assert len(state["review_revisions"]) == 1
    assert (
        saved_review.service.get_batch(saved_review.batch["id"])["revision"]
        == saved_review.batch["revision"] + 1
    )


@pytest.mark.parametrize(
    "details,message",
    [
        ({"coverage_status": "invalid"}, "语义覆盖状态不合法"),
        (
            {
                "semantic_item_reviews": [
                    {"semantic_item_id": "foreign", "action": "remove"}
                ]
            },
            "选择的语义核验项不存在",
        ),
        (
            {
                "added_semantic_items": [
                    {"label_code": "MISSING", "evidence_text": "foreign"}
                ]
            },
            "选择的语义标签不存在",
        ),
    ],
)
def test_invalid_details_leave_records_revisions_events_and_audits_unchanged(
    saved_review: SimpleNamespace, details: dict[str, Any], message: str
) -> None:
    before = _database_state(saved_review.database)
    record = saved_review.review
    with pytest.raises(ValueError) as caught:
        saved_review.service.update_batch_record(
            saved_review.batch["id"],
            record["id"],
            record["revision"],
            "user-1",
            None,
            "拒绝非法详情",
            action="confirm",
            **details,
        )
    assert str(caught.value) == message
    assert _database_state(saved_review.database) == before


def test_bulk_update_rolls_back_prior_record_when_later_record_is_invalid(
    saved_review: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = saved_review.review
    with saved_review.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id, classification_key,
                comment, workflow_status, classification_json, revision, updated_at
            )
            SELECT 'invalid-review', task_id, batch_id, base_result_version_id,
                   'invalid-key', comment, 'pending', ?, 1, updated_at
            FROM review_records WHERE id = ?
            """,
            (
                json.dumps(
                    {"semantic_units": [], "unknown_semantics": [{"opinion": "待判断"}]}
                ),
                record["id"],
            ),
        )
    before = _database_state(saved_review.database)
    update_row = Mock(wraps=saved_review.service._update_batch_record_row)
    monkeypatch.setattr(saved_review.service, "_update_batch_record_row", update_row)

    with pytest.raises(ValueError, match="未知语义必须选择一个标签后才能完成复核"):
        saved_review.service.update_batch_records(
            saved_review.batch["id"],
            [
                {"id": record["id"], "expected_revision": record["revision"]},
                {"id": "invalid-review", "expected_revision": 1},
            ],
            "user-1",
            "confirm",
            None,
            "验证整批回滚",
        )
    assert update_row.call_count == 2
    assert _database_state(saved_review.database) == before

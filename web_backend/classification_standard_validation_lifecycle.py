from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from return_semantics.capabilities import resolve_model_policy
from web_backend.classification_standard_service import (
    ClassificationStandardConflict,
    ClassificationStandardService,
)
from web_backend.classification_standard_validation_contracts import (
    ClassificationStandardValidationConflict,
)
from web_backend.classification_standard_validation_leakage import (
    find_taxonomy_sample_leaks,
    format_taxonomy_sample_leaks,
)
from web_backend.common import add_audit, json_text, new_id
from web_backend.database import Database
from web_backend.model_preference_service import ModelPreferenceService
from web_backend.security import utc_now


class ClassificationStandardValidationLifecycleMixin:
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def get(
            self,
            run_id: str,
            include_items: bool = True,
        ) -> dict[str, Any]: ...

        _validation_source_context: Callable[
            [dict[str, Any], str, int, tuple[str, bytes] | None],
            tuple[dict[str, Any], list[dict[str, Any]], str],
        ]

        def _apply_recognition_context(
            self,
            source: dict[str, Any],
            draft: dict[str, Any],
            draft_id: str,
            expected_revision: int,
            comparison_type: str,
        ) -> None: ...

    def create_run(
        self,
        draft_id: str,
        expected_revision: int,
        source_result_version_id: str,
        sample_size: int,
        actor_id: str,
        review_file: tuple[str, bytes] | None = None,
        comparison_type: str = "standard_version",
    ) -> dict[str, Any]:
        if comparison_type not in {"standard_version", "keyword_ab", "semantic_ab"}:
            raise ValueError("不支持的验证目的")
        if sample_size not in {20, 50, 100}:
            raise ValueError("样本规模必须为20、50或100")
        draft = self.standard_service.get_draft(draft_id)
        if int(draft["revision"]) != expected_revision:
            raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
        if draft["validation"]["blocking"]:
            detail = "；".join(draft["validation"]["blocking"][:3])
            raise ValueError(f"草稿必须先通过结构检查：{detail}")
        source, samples, source_result_version_id = self._validation_source_context(
            draft,
            source_result_version_id,
            sample_size,
            review_file,
        )
        if not samples:
            raise ValueError("所选数据中没有当前品类可用于验证的评论")
        leakage_issues = find_taxonomy_sample_leaks(
            draft["snapshot"]["taxonomy"],
            samples,
        )
        if leakage_issues:
            raise ValueError(format_taxonomy_sample_leaks(leakage_issues))
        self._apply_recognition_context(
            source,
            draft,
            draft_id,
            expected_revision,
            comparison_type,
        )
        self._freeze_model_context(source, draft, actor_id)
        run_id = new_id("classification_standard_validation")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            active = connection.execute(
                """
                SELECT id FROM classification_standard_validation_runs
                WHERE draft_id = ? AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (draft_id,),
            ).fetchone()
            if active is not None:
                raise ClassificationStandardValidationConflict(
                    "当前草稿已有样本验证正在运行"
                )
            connection.execute(
                """
                INSERT INTO classification_standard_validation_runs(
                    id, standard_id, draft_id, draft_revision,
                    base_version_id, source_result_version_id,
                    config_version_id, status, stage, sample_size,
                    snapshot_json, source_json, sample_json,
                    created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    draft["standard_id"],
                    draft_id,
                    expected_revision,
                    draft["base_version_id"],
                    source_result_version_id,
                    source.get("config_version_id")
                    or source["task"]["config_version_id"],
                    len(samples),
                    json_text(draft["snapshot"]),
                    json_text(source),
                    json_text(samples),
                    actor_id,
                    now,
                ),
            )
        add_audit(
            self.database,
            "classification_standard_validation",
            run_id,
            "create",
            actor_id,
            after={
                "draft_id": draft_id,
                "draft_revision": expected_revision,
                "source_result_version_id": source_result_version_id,
                "sample_size": len(samples),
            },
        )
        return self.get(run_id)

    def _freeze_model_context(
        self,
        source: dict[str, Any],
        draft: dict[str, Any],
        actor_id: str,
    ) -> None:
        preference = ModelPreferenceService(self.database).task_policy(actor_id)
        if preference is None:
            return
        capability = self.standard_service._capability_from_snapshot(draft["snapshot"])
        source["config_version_id"] = str(preference["config_version_id"])
        source["model_policy"] = resolve_model_policy(capability, preference)

    def approve(
        self,
        run_id: str,
        expected_revision: int,
        note: str,
        actor_id: str,
    ) -> dict[str, Any]:
        validation = self.get(run_id)
        if (
            validation["source"].get("comparison_type", "standard_version")
            != "standard_version"
        ):
            raise ValueError("策略对照仅用于诊断，不能代替发布验证")
        if not validation["is_current"] or int(validation["draft_revision"]) != int(
            expected_revision
        ):
            raise ClassificationStandardValidationConflict(
                "验证结果不属于当前草稿修订，请重新运行"
            )
        if validation["status"] != "completed":
            raise ValueError("样本验证尚未完成")
        if int(validation["error_count"]) > 0:
            raise ValueError("样本验证存在模型错误，不能确认通过")
        if not validation["quality_gate"]["passed"]:
            raise ValueError(
                "质量门槛未通过：" + "；".join(validation["quality_gate"]["blocking"])
            )
        approval_note = note.strip()
        if not approval_note:
            raise ValueError("请填写验证结论")
        approved_at = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE classification_standard_validation_runs
                SET approved_by = ?, approved_at = ?, approval_note = ?
                WHERE id = ?
                """,
                (actor_id, approved_at, approval_note, run_id),
            )
        add_audit(
            self.database,
            "classification_standard_validation",
            run_id,
            "approve",
            actor_id,
            after={
                "draft_revision": expected_revision,
                "note": approval_note,
            },
        )
        return self.get(run_id)

    def recover(self) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE classification_standard_validation_runs
                SET status = 'queued', stage = 'queued', error = NULL,
                    processed_count = 0, started_at = NULL
                WHERE status = 'running'
                """
            )

    def claim_next(self) -> str | None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT id FROM classification_standard_validation_runs
                WHERE status = 'queued'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            run_id = str(row["id"])
            updated = connection.execute(
                """
                UPDATE classification_standard_validation_runs
                SET status = 'running', stage = 'calling_model',
                    started_at = ?, error = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (utc_now(), run_id),
            )
        return run_id if updated.rowcount == 1 else None

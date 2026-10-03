from __future__ import annotations

from typing import TYPE_CHECKING, Any

from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standards.validation_raw_sources import (
    ClassificationStandardValidationRawSourcesMixin,
)
from web_backend.classification_standards.validation_recognition import (
    ClassificationStandardValidationRecognitionMixin,
)
from web_backend.classification_standards.validation_sampling import (
    ClassificationStandardValidationSamplingMixin,
)
from web_backend.database import Database


class ClassificationStandardValidationSourcesMixin(
    ClassificationStandardValidationRawSourcesMixin,
    ClassificationStandardValidationRecognitionMixin,
    ClassificationStandardValidationSamplingMixin,
):
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def _review_source_context(
            self,
            filename: str,
            content: bytes,
            draft: dict[str, Any],
            sample_size: int,
        ) -> tuple[dict[str, Any], list[dict[str, Any]]]: ...

    def sources(self, draft_id: str) -> list[dict[str, Any]]:
        draft = self.standard_service.get_draft(draft_id)
        raw_sources = [item["public"] for item in self._raw_source_options()]
        if draft["is_new"]:
            return raw_sources
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.id AS result_version_id, v.version_no,
                       v.quality_status, v.unit_count, v.record_count,
                       v.published_at, r.store_site, r.listing,
                       (
                           SELECT COUNT(*) FROM classification_units unit
                           WHERE unit.result_version_id = v.id
                             AND TRIM(COALESCE(unit.comment, '')) != ''
                             AND unit.quality_status != 'excluded'
                       ) AS available_sample_count
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE r.standard_version_id = ?
                  AND v.publish_status = 'published'
                  AND EXISTS (
                      SELECT 1 FROM classification_units unit
                      WHERE unit.result_version_id = v.id
                        AND TRIM(COALESCE(unit.comment, '')) != ''
                        AND unit.quality_status != 'excluded'
                  )
                ORDER BY v.published_at DESC, v.id DESC
                """,
                (draft["base_version_id"],),
            ).fetchall()
        return [*raw_sources, *(dict(row) for row in rows)]

    def _validation_source_context(
        self,
        draft: dict[str, Any],
        source_result_version_id: str,
        sample_size: int,
        review_file: tuple[str, bytes] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        raw_source_ids = {item["id"] for item in self._raw_source_options()}
        if review_file is not None:
            source, samples = self._review_source_context(
                review_file[0], review_file[1], draft, sample_size
            )
            return source, samples, source["result"]["result_version_id"]
        if source_result_version_id in raw_source_ids:
            source, samples = self._raw_source_context(
                source_result_version_id,
                draft,
                sample_size,
            )
            return source, samples, source_result_version_id
        source = self._source_context(
            source_result_version_id,
            str(draft["base_version_id"]),
        )
        return (
            source,
            self._sample(source_result_version_id, sample_size),
            source_result_version_id,
        )

    def _published_config_id(self) -> str:
        with self.database.connect() as connection:
            config = connection.execute(
                """
                SELECT v.id
                FROM api_connections c
                JOIN api_config_versions v ON v.id = c.active_version_id
                WHERE v.published_at IS NOT NULL
                ORDER BY c.updated_at DESC, v.id
                LIMIT 1
                """
            ).fetchone()
        if config is None:
            raise ValueError("请先验证并发布一个模型服务配置")
        return str(config["id"])

    def _source_context(
        self,
        result_version_id: str,
        base_version_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            result = connection.execute(
                """
                SELECT v.id AS result_version_id, v.version_no,
                       v.quality_status, v.unit_count, v.record_count,
                       v.published_at, r.store_site, r.listing,
                       r.standard_version_id,
                       r.source_task_id, r.source_segment_id
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE v.id = ? AND v.publish_status = 'published'
                """,
                (result_version_id,),
            ).fetchone()
            if result is None:
                raise ValueError("所选分类结果不存在或尚未发布")
            if result["standard_version_id"] != base_version_id:
                raise ValueError("所选分类结果不属于草稿的基础标准版本")
            task = connection.execute(
                """
                SELECT id, config_version_id, store, listing, snapshot_json
                FROM tasks WHERE id = ?
                """,
                (result["source_task_id"],),
            ).fetchone()
            segment = connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (result["source_segment_id"],),
            ).fetchone()
        if task is None or segment is None:
            raise ValueError("分类结果缺少可复用的任务执行上下文")
        public_result = dict(result)
        public_result.pop("source_task_id", None)
        public_result.pop("source_segment_id", None)
        return {
            "result": public_result,
            "task": dict(task),
            "segment": dict(segment),
        }

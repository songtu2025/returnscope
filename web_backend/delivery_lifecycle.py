"""分类结果、看板的可恢复删除以及洞察生成取消。"""

from typing import Any

from web_backend.common import insert_audit
from web_backend.database import Database
from web_backend.security import utc_now


class DeliveryLifecycleConflict(ValueError):
    pass


def require_active_segment_result(connection: Any, segment_id: str) -> None:
    removed = connection.execute(
        """SELECT 1 FROM task_segments s
           JOIN classification_result_versions v ON v.id=s.result_version_id
           JOIN classification_results r ON r.id=v.result_id
           WHERE s.id=? AND r.deleted_at IS NOT NULL""",
        (segment_id,),
    ).fetchone()
    if removed:
        raise ValueError("请先恢复分类结果，再继续或重试分析")


class DeliveryLifecycleService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def report(
        self, report_id: str, *, revision: int, deleted: bool, actor: str
    ) -> None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM ai_insight_reports WHERE id=?", (report_id,)
            ).fetchone()
            self._validate(row, revision, deleted)
            if row["status"] in {"queued", "running"}:
                raise DeliveryLifecycleConflict("请先取消正在生成的报告")
            if (
                not deleted
                and connection.execute(
                    "SELECT 1 FROM analysis_dashboards WHERE id=? AND deleted_at IS NOT NULL",
                    (row["dashboard_id"],),
                ).fetchone()
            ):
                raise DeliveryLifecycleConflict("请先恢复分析看板")
            now = utc_now()
            connection.execute(
                "UPDATE ai_insight_reports SET deleted_at=?, revision=revision+1 WHERE id=?",
                (now if deleted else None, report_id),
            )
            insert_audit(
                connection,
                "ai_insight_report",
                report_id,
                "delete" if deleted else "restore",
                actor,
                {"deleted_at": row["deleted_at"]},
                {"deleted_at": now if deleted else None},
                now,
            )

    @staticmethod
    def _validate(row: Any, revision: int, deleted: bool) -> None:
        if row is None:
            raise ValueError("对象不存在")
        if row["revision"] != revision:
            raise DeliveryLifecycleConflict("对象已更新，请刷新后重试")
        if bool(row["deleted_at"]) == deleted:
            raise DeliveryLifecycleConflict("对象已删除" if deleted else "对象未删除")

    def result(
        self, version_id: str, *, revision: int, deleted: bool, actor: str
    ) -> None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """SELECT r.* FROM classification_results r
                   JOIN classification_result_versions v ON v.result_id=r.id
                   WHERE v.id=?""",
                (version_id,),
            ).fetchone()
            self._validate(row, revision, deleted)
            if deleted:
                dashboards = connection.execute(
                    """SELECT DISTINCT d.name FROM analysis_dashboards d
                       JOIN dashboard_versions dv ON dv.id=d.current_version_id
                       JOIN dashboard_dataset_sources s ON s.dataset_version_id=dv.dataset_version_id
                       JOIN classification_result_versions v ON v.id=s.result_version_id
                       WHERE d.deleted_at IS NULL AND v.result_id=?""",
                    (row["id"],),
                ).fetchall()
                if dashboards:
                    raise DeliveryLifecycleConflict(
                        "请先解除引用或删除关联看板："
                        + "、".join(d["name"] for d in dashboards)
                    )
                segment = connection.execute(
                    "SELECT status, deleted_at, removal_requested_at FROM task_segments WHERE id=?",
                    (row["source_segment_id"],),
                ).fetchone()
                if segment and (
                    segment["status"] == "running" or segment["removal_requested_at"]
                ):
                    raise DeliveryLifecycleConflict(
                        "来源 Listing 正在执行或移除中，请等待执行停止后再删除分类结果"
                    )
                if (
                    segment
                    and not segment["deleted_at"]
                    and segment["status"]
                    in {
                        "queued",
                        "retry_pending",
                        "paused",
                        "not_started",
                    }
                ):
                    raise DeliveryLifecycleConflict(
                        "请先在分析任务中移除来源 Listing，再删除分类结果"
                    )
            now = utc_now()
            connection.execute(
                "UPDATE classification_results SET deleted_at=?, revision=revision+1 WHERE id=?",
                (now if deleted else None, row["id"]),
            )
            connection.execute(
                "UPDATE tasks SET revision=revision+1, heartbeat_at=? WHERE id=?",
                (now, row["source_task_id"]),
            )
            connection.execute(
                "UPDATE task_segments SET revision=revision+1 WHERE id=?",
                (row["source_segment_id"],),
            )
            insert_audit(
                connection,
                "classification_result",
                row["id"],
                "delete" if deleted else "restore",
                actor,
                {"deleted_at": row["deleted_at"]},
                {"deleted_at": now if deleted else None},
            )

    def dashboard(
        self, dashboard_id: str, *, revision: int, deleted: bool, actor: str
    ) -> None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM analysis_dashboards WHERE id=?", (dashboard_id,)
            ).fetchone()
            self._validate(row, revision, deleted)
            if deleted:
                running = connection.execute(
                    "SELECT 1 FROM ai_insight_reports WHERE dashboard_id=? AND status IN ('queued','running')",
                    (dashboard_id,),
                ).fetchone()
                if running:
                    raise DeliveryLifecycleConflict(
                        "请先取消正在生成的 AI 洞察，再删除看板"
                    )
            else:
                missing = connection.execute(
                    """SELECT 1 FROM dashboard_versions dv
                       JOIN dashboard_dataset_sources s ON s.dataset_version_id=dv.dataset_version_id
                       JOIN classification_result_versions v ON v.id=s.result_version_id
                       JOIN classification_results r ON r.id=v.result_id
                       WHERE dv.id=? AND r.deleted_at IS NOT NULL""",
                    (row["current_version_id"],),
                ).fetchone()
                if missing:
                    raise DeliveryLifecycleConflict("请先恢复被此看板引用的分类结果")
            now = utc_now()
            connection.execute(
                "UPDATE analysis_dashboards SET deleted_at=?, updated_at=?, revision=revision+1 WHERE id=?",
                (now if deleted else None, now, dashboard_id),
            )
            insert_audit(
                connection,
                "analysis_dashboard",
                dashboard_id,
                "delete" if deleted else "restore",
                actor,
                {"deleted_at": row["deleted_at"]},
                {"deleted_at": now if deleted else None},
            )
            if not deleted:
                from web_backend.dashboards.live_sources import (
                    refresh_related_dashboards,
                )

                datasets = connection.execute(
                    """SELECT DISTINCT product.dataset_id FROM dashboard_versions dv
                       JOIN dashboard_dataset_sources s ON s.dataset_version_id=dv.dataset_version_id
                       JOIN classification_result_versions v ON v.id=s.result_version_id
                       JOIN classification_results r ON r.id=v.result_id
                       JOIN dataset_versions product ON product.id=r.product_version_id
                       WHERE dv.id=?""",
                    (row["current_version_id"],),
                ).fetchall()
                for dataset in datasets:
                    refresh_related_dashboards(
                        self.database,
                        connection,
                        None,
                        now,
                        product_dataset_id=dataset["dataset_id"],
                        dashboard_id=dashboard_id,
                    )

    def cancel_report(self, report_id: str, actor: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT status FROM ai_insight_reports WHERE id=?", (report_id,)
            ).fetchone()
            if row is None:
                raise ValueError("生成任务不存在")
            if row["status"] not in {"queued", "running"}:
                raise DeliveryLifecycleConflict("本次生成已结束，请刷新后查看")
            now = utc_now()
            connection.execute(
                """UPDATE ai_insight_reports SET status='failed', stage='cancelled',
                   cancelled_at=?, completed_at=?, error=NULL, technical_error=NULL WHERE id=?""",
                (now, now, report_id),
            )
            insert_audit(
                connection,
                "ai_insight_report",
                report_id,
                "cancel",
                actor,
                {"status": row["status"]},
                {"status": "cancelled"},
            )

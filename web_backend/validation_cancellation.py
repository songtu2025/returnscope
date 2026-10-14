"""取消验证只终止本次执行，保留此前有效的服务配置与标准。"""

from typing import Literal

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.security import utc_now


def cancel_validation(
    database: Database, kind: Literal["model", "standard"], run_id: str, actor: str
) -> None:
    table = (
        "api_validation_runs"
        if kind == "model"
        else "classification_standard_validation_runs"
    )
    status = "cancelled" if kind == "model" else "failed"
    with database.transaction(immediate=True) as connection:
        row = connection.execute(
            f"SELECT status, stage FROM {table} WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise ValueError("验证记录不存在")
        if row["stage"] == "cancelled":
            return
        if row["status"] not in {"queued", "running"}:
            raise ValueError("验证已结束，无法取消")
        connection.execute(
            f"UPDATE {table} SET status=?, stage='cancelled', completed_at=? WHERE id=?",
            (status, utc_now(), run_id),
        )
        if kind == "model":
            connection.execute(
                "INSERT INTO api_validation_events(run_id, event_type, stage, "
                "message, data_json, created_at) VALUES (?, 'cancelled', 'cancelled', "
                "'本次验证已取消', '{}', ?)",
                (run_id, utc_now()),
            )
    add_audit(database, f"{kind}_validation", run_id, "cancel", actor)

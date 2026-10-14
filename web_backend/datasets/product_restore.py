"""还原人工修改；重新导入改变行序后不凭旧行号覆盖产品。"""

from typing import Any

from web_backend.common import json_value


def restore_product_edit(
    service: Any, dataset_id: str, audit_id: str, expected_version: int, actor: str
) -> dict[str, Any]:
    with service.database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM audit_logs WHERE id=? AND entity_type='dataset' "
            "AND entity_id=? AND action='dimension_row_update'",
            (audit_id, dataset_id),
        ).fetchone()
        if row is None:
            raise ValueError("可还原的产品修改记录不存在")
        if connection.execute(
            "SELECT 1 FROM audit_logs WHERE entity_type='dataset' AND entity_id=? "
            "AND action='product_update' AND created_at>=?",
            (dataset_id, row["created_at"]),
        ).fetchone():
            raise ValueError("此后已重新导入产品资料，请核对当前产品后手动修改")
        before = json_value(row["before_json"], {})
    return service.update_product_row(
        dataset_id=dataset_id,
        row_index=int(before["row_index"]),
        expected_version=expected_version,
        changes=before["values"],
        change_note=f"还原 {row['created_at']} 的人工修改",
        actor_id=actor,
    )

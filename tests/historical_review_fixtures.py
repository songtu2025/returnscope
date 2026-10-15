"""构造已存在的历史复核批次，不调用已退役的业务写入口。"""

from web_backend.review_service import ReviewService


def historical_batch(context, version):
    batch_id = "historical-batch"
    version_id = version["version_id"]
    now = "2026-08-12T00:04:00+00:00"
    with context.database.transaction() as connection:
        connection.execute(
            "INSERT INTO review_batches(id,base_result_version_id,result_id,status,revision,created_by,created_at,updated_at) VALUES(?,?,?,'draft',1,'user-1',?,?)",
            (batch_id, version_id, version["result_id"], now, now),
        )
        connection.execute(
            """INSERT INTO review_records(id,task_id,batch_id,base_result_version_id,
               classification_key,comment,workflow_status,classification_json,revision,updated_at)
               SELECT 'historical-review',?, ?, result_version_id,classification_key,
                      comment,'pending',classification_json,1,? FROM classification_units
               WHERE result_version_id=? AND classification_key=?""",
            (context.task_id, batch_id, now, version_id, context.key),
        )
    return ReviewService(context.database).get_batch(batch_id)

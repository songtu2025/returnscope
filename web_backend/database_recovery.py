from __future__ import annotations

import secrets
import sqlite3


def recover_interrupted_result_publishing(connection: sqlite3.Connection) -> None:
    """应用重启时将未完成的结果发布标记为失败。"""
    connection.execute(
        """
        UPDATE classification_result_versions
        SET publish_status = 'failed'
        WHERE publish_status = 'publishing'
        """
    )
    connection.execute(
        """
        UPDATE task_segments
        SET result_publish_status = 'failed',
            result_publish_error = COALESCE(
                result_publish_error,
                '服务重启时发现结果发布未完成，请重试发布'
            )
        WHERE result_publish_status = 'publishing'
          AND NOT EXISTS (
              SELECT 1 FROM classification_result_versions v
              WHERE v.source_segment_id = task_segments.id
                AND v.publish_status = 'published'
          )
        """
    )


def sync_api_models(connection: sqlite3.Connection) -> None:
    """启动时同步历史模型配置中的模型目录。"""
    model_rows = connection.execute(
        """
        SELECT connection_id, primary_model AS model_key,
               validation_status, validation_message, validated_at,
               created_by, created_at
        FROM api_config_versions
        UNION ALL
        SELECT connection_id, cheap_model AS model_key,
               validation_status, validation_message, validated_at,
               created_by, created_at
        FROM api_config_versions
        WHERE cheap_model IS NOT NULL
        UNION ALL
        SELECT connection_id, secondary_model AS model_key,
               validation_status, validation_message, validated_at,
               created_by, created_at
        FROM api_config_versions
        WHERE secondary_model IS NOT NULL
        ORDER BY created_at
        """
    ).fetchall()
    for row in model_rows:
        model_id = f"model_{secrets.token_hex(8)}"
        connection.execute(
            """
            INSERT INTO api_models(
                id, connection_id, model_key, display_name,
                supported_efforts_json, active, validation_status,
                validation_message, validated_at, created_by,
                created_at, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, '["low","medium","high"]', 1,
                      ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(connection_id, model_key) DO UPDATE SET
                validation_status = CASE
                    WHEN excluded.validation_status = 'validated'
                    THEN 'validated'
                    ELSE api_models.validation_status
                END,
                validation_message = CASE
                    WHEN excluded.validation_status = 'validated'
                    THEN excluded.validation_message
                    ELSE api_models.validation_message
                END,
                validated_at = CASE
                    WHEN excluded.validation_status = 'validated'
                    THEN excluded.validated_at
                    ELSE api_models.validated_at
                END
            """,
            (
                model_id,
                row["connection_id"],
                row["model_key"],
                row["model_key"],
                row["validation_status"],
                row["validation_message"],
                row["validated_at"],
                row["created_by"],
                row["created_at"],
                row["created_by"],
                row["created_at"],
            ),
        )

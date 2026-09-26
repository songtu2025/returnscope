from __future__ import annotations

import sqlite3


class DatabaseTableRebuilds:
    @staticmethod
    def _migrate_review_records(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(review_records)"
            ).fetchall()
        }
        table_sql_row = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'review_records'
            """
        ).fetchone()
        table_sql = str(table_sql_row["sql"] or "") if table_sql_row else ""
        if (
            "batch_id" in columns
            and "UNIQUE(task_id, classification_key)" not in table_sql
        ):
            return

        foreign_keys_enabled = bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("SAVEPOINT migrate_review_records")
        try:
            connection.execute(
                "ALTER TABLE review_revisions RENAME TO legacy_review_revisions"
            )
            connection.execute(
                "ALTER TABLE review_records RENAME TO legacy_review_records"
            )
            connection.execute(
                """
                CREATE TABLE review_records (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                batch_id TEXT REFERENCES review_batches(id) ON DELETE CASCADE,
                base_result_version_id TEXT
                    REFERENCES classification_result_versions(id),
                classification_key TEXT NOT NULL,
                comment TEXT NOT NULL,
                workflow_status TEXT NOT NULL DEFAULT 'pending',
                classification_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                updated_by TEXT REFERENCES users(id),
                updated_at TEXT NOT NULL,
                UNIQUE(batch_id, classification_key)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_by, updated_at
                )
                SELECT id, task_id, NULL, NULL, classification_key, comment,
                       workflow_status, classification_json, revision,
                       updated_by, updated_at
                FROM legacy_review_records
                """
            )
            connection.execute(
                """
                CREATE TABLE review_revisions (
                id TEXT PRIMARY KEY,
                review_record_id TEXT NOT NULL REFERENCES review_records(id),
                revision INTEGER NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO review_revisions(
                id, review_record_id, revision, before_json, after_json,
                note, actor_id, created_at
                )
                SELECT id, review_record_id, revision, before_json, after_json,
                       note, actor_id, created_at
                FROM legacy_review_revisions
                """
            )
            connection.execute("DROP TABLE legacy_review_revisions")
            connection.execute("DROP TABLE legacy_review_records")
            connection.execute(
                """
                CREATE INDEX idx_review_records_status
                ON review_records(workflow_status, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX idx_review_records_batch
                ON review_records(batch_id, updated_at DESC, id)
                """
            )
        except Exception:
            connection.execute("ROLLBACK TO SAVEPOINT migrate_review_records")
            connection.execute("RELEASE SAVEPOINT migrate_review_records")
            raise
        else:
            connection.execute("RELEASE SAVEPOINT migrate_review_records")
        finally:
            if foreign_keys_enabled:
                connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _migrate_excluded_quality_status(
        connection: sqlite3.Connection,
    ) -> None:
        table_sql = {
            str(row["name"]): str(row["sql"] or "")
            for row in connection.execute(
                """
                SELECT name, sql FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                      'classification_units',
                      'classification_result_records'
                  )
                """
            ).fetchall()
        }
        if all("'excluded'" in sql for sql in table_sql.values()):
            return

        foreign_keys_enabled = bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("SAVEPOINT migrate_excluded_quality_status")
        try:
            if "'excluded'" not in table_sql.get("classification_units", ""):
                connection.execute(
                    "ALTER TABLE classification_units RENAME TO legacy_classification_units"
                )
                connection.execute("DROP INDEX idx_classification_units_quality")
                connection.execute(
                    """
                    CREATE TABLE classification_units (
                        id TEXT PRIMARY KEY,
                        result_version_id TEXT NOT NULL
                            REFERENCES classification_result_versions(id)
                            ON DELETE CASCADE,
                        classification_key TEXT NOT NULL,
                        reason TEXT,
                        comment TEXT,
                        classification_json TEXT NOT NULL,
                        problem_labels_json TEXT NOT NULL DEFAULT '[]',
                        system_rerun_required INTEGER NOT NULL DEFAULT 0
                            CHECK(system_rerun_required IN (0, 1)),
                        processing_status TEXT NOT NULL,
                        quality_status TEXT NOT NULL CHECK(
                            quality_status IN (
                                'ready', 'review_required', 'unusable', 'excluded'
                            )
                        ),
                        record_count INTEGER NOT NULL DEFAULT 0,
                        model_name TEXT,
                        prompt_version TEXT,
                        taxonomy_version TEXT,
                        UNIQUE(result_version_id, classification_key)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO classification_units(
                        id, result_version_id, classification_key,
                        reason, comment, classification_json,
                        problem_labels_json, processing_status,
                        quality_status, record_count, model_name,
                        prompt_version, taxonomy_version
                    )
                    SELECT id, result_version_id, classification_key,
                           reason, comment, classification_json,
                           problem_labels_json, processing_status,
                           quality_status, record_count, model_name,
                           prompt_version, taxonomy_version
                    FROM legacy_classification_units
                    """
                )
                connection.execute("DROP TABLE legacy_classification_units")
                connection.execute(
                    """
                    CREATE INDEX idx_classification_units_quality
                    ON classification_units(
                        result_version_id, quality_status, classification_key
                    )
                    """
                )
            if "'excluded'" not in table_sql.get(
                "classification_result_records",
                "",
            ):
                connection.execute(
                    """
                    ALTER TABLE classification_result_records
                    RENAME TO legacy_classification_result_records
                    """
                )
                record_indexes = [
                    "idx_classification_records_listing",
                    "idx_classification_records_source_row",
                    "idx_classification_records_order",
                    "idx_classification_records_source_sku",
                    "idx_classification_records_matched_msku",
                    "idx_classification_records_product_sku",
                    "idx_classification_records_product_name",
                    "idx_classification_records_asin",
                    "idx_classification_records_quality",
                    "idx_classification_records_unit",
                ]
                for index_name in record_indexes:
                    connection.execute(f"DROP INDEX {index_name}")
                connection.execute(
                    """
                    CREATE TABLE classification_result_records (
                        id TEXT PRIMARY KEY,
                        result_version_id TEXT NOT NULL
                            REFERENCES classification_result_versions(id)
                            ON DELETE CASCADE,
                        classification_key TEXT NOT NULL,
                        source_record_id TEXT NOT NULL,
                        source_row INTEGER NOT NULL,
                        return_date TEXT,
                        order_id TEXT,
                        store_site TEXT,
                        listing TEXT,
                        product_name TEXT,
                        source_sku TEXT,
                        matched_msku TEXT,
                        product_sku TEXT,
                        asin TEXT,
                        fnsku TEXT,
                        category_a TEXT,
                        category_b TEXT,
                        reason TEXT,
                        comment TEXT,
                        product_match_status TEXT NOT NULL,
                        quality_status TEXT NOT NULL CHECK(
                            quality_status IN (
                                'ready', 'review_required', 'unusable', 'excluded'
                            )
                        ),
                        UNIQUE(result_version_id, source_record_id)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO classification_result_records
                    SELECT * FROM legacy_classification_result_records
                    """
                )
                connection.execute("DROP TABLE legacy_classification_result_records")
                record_index_columns = {
                    "listing": "listing, source_row",
                    "source_row": "source_row, id",
                    "order": "order_id, source_row",
                    "source_sku": "source_sku, source_row",
                    "matched_msku": "matched_msku, source_row",
                    "product_sku": "product_sku, source_row",
                    "product_name": "product_name, source_row",
                    "asin": "asin, source_row",
                    "quality": "quality_status, source_row",
                    "unit": "classification_key, quality_status",
                }
                for suffix, columns in record_index_columns.items():
                    connection.execute(
                        "CREATE INDEX idx_classification_records_"
                        f"{suffix} ON classification_result_records("
                        f"result_version_id, {columns})"
                    )
        except Exception:
            connection.execute("ROLLBACK TO SAVEPOINT migrate_excluded_quality_status")
            connection.execute("RELEASE SAVEPOINT migrate_excluded_quality_status")
            raise
        else:
            connection.execute("RELEASE SAVEPOINT migrate_excluded_quality_status")
        finally:
            if foreign_keys_enabled:
                connection.execute("PRAGMA foreign_keys = ON")

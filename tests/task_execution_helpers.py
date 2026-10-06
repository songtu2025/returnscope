import sqlite3


def trace_queries(database, monkeypatch) -> list[str]:
    queries: list[str] = []
    original = database.connect

    def connect():
        connection = original()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(database, "connect", connect)
    return queries


def transaction_statements(queries: list[str]) -> list[str]:
    statements = [" ".join(query.split()) for query in queries]
    begin = statements.index("BEGIN IMMEDIATE")
    end = statements.index("COMMIT", begin)
    return statements[begin + 1 : end]


def fail_event_write(database) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            CREATE TRIGGER synthetic_event_failure BEFORE INSERT ON task_events
            BEGIN SELECT RAISE(ABORT, '合成回滚'); END
            """
        )


def segment_rows(database, task_id) -> dict:
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM task_segments WHERE task_id = ?", (task_id,)
        ).fetchall()
    return {row["id"]: dict(row) for row in rows}


def audit_rows(database) -> list[dict]:
    with database.connect() as connection:
        rows = connection.execute("SELECT * FROM audit_logs ORDER BY id").fetchall()
    return [dict(row) for row in rows]


EVENT_FAILURE = sqlite3.IntegrityError

from __future__ import annotations

import json
import time
from typing import Any, Callable

from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.model_catalog import ModelCatalogService, validate_effort
from web_backend.model_probe import ModelProbe, ModelValidationError
from web_backend.security import utc_now


class ValidationRunService:
    def __init__(
        self,
        database: Database,
        model_catalog: ModelCatalogService,
        model_probe: ModelProbe,
        get_version: Callable[..., dict[str, Any] | None],
    ) -> None:
        self.database = database
        self.model_catalog = model_catalog
        self.model_probe = model_probe
        self.get_version = get_version

    def start_model_validation(
        self,
        model_id: str,
        actor_id: str,
        effort: str | None = None,
    ) -> dict[str, Any]:
        model = self.model_catalog.get(model_id)
        if model is None:
            raise ValueError("模型不存在")
        if not model["active"]:
            raise ValueError("停用模型不能验证")
        chosen_effort = effort or (
            "medium"
            if "medium" in model["supported_efforts"]
            else model["supported_efforts"][0]
        )
        chosen_effort = validate_effort(chosen_effort, "模型推理强度")
        if chosen_effort not in model["supported_efforts"]:
            raise ValueError("所选推理强度不在模型支持范围内")
        with self.database.connect() as connection:
            version = connection.execute(
                """
                SELECT id FROM api_config_versions
                WHERE connection_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (model["connection_id"],),
            ).fetchone()
        if version is None:
            raise ValueError("请先保存 API 接入配置，再验证模型")
        config = self.get_version(str(version["id"]))
        if config is None:
            raise ValueError("API 配置不存在")
        return self._create_validation_run(
            kind="model",
            target_id=model_id,
            connection_id=str(model["connection_id"]),
            config_version_id=str(version["id"]),
            actor_id=actor_id,
            config=config,
            items=[
                self._validation_item(
                    model,
                    chosen_effort,
                    "单模型验证",
                )
            ],
        )

    def start_config_validation(
        self,
        version_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        config = self.get_version(version_id)
        if config is None:
            raise ValueError("配置版本不存在")
        pipeline = [
            (config.get("cheap_model"), config["cheap_effort"], "低成本初筛"),
            (config["primary_model"], config["primary_effort"], "主分析"),
            (
                config.get("secondary_model"),
                config["secondary_effort"],
                "风险二次复核",
            ),
        ]
        with self.database.connect() as connection:
            self.model_catalog.ensure_pipeline_models(
                connection,
                str(config["connection_id"]),
                [(model, effort) for model, effort, _role in pipeline],
            )
        items: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for model_key, effort, role in pipeline:
            if not model_key:
                continue
            existing = by_key.get(str(model_key))
            if existing:
                existing["role"] = f"{existing['role']} / {role}"
                continue
            model = self.model_catalog.get_by_key(
                str(config["connection_id"]),
                str(model_key),
            )
            if model is None:
                raise ValueError(f"模型 {model_key} 不存在")
            item = self._validation_item(model, str(effort), role)
            items.append(item)
            by_key[str(model_key)] = item
        return self._create_validation_run(
            kind="config",
            target_id=version_id,
            connection_id=str(config["connection_id"]),
            config_version_id=version_id,
            actor_id=actor_id,
            config=config,
            items=items,
        )

    def get_validation_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, u.display_name AS creator_name
                FROM api_validation_runs r
                JOIN users u ON u.id = r.created_by
                WHERE r.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["items"] = json.loads(item.pop("items_json"))
        return item

    def latest_active_validation_run(
        self,
        connection_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE connection_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (connection_id,),
            ).fetchone()
        return self.get_validation_run(str(row["id"])) if row else None

    def validation_events(
        self,
        run_id: str,
        after_id: int = 0,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM api_validation_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (run_id, after_id),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json") or "{}")
            output.append(item)
        return output

    def recover_validation_runs(self) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE status IN ('queued', 'running')
                """
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE api_validation_runs
                    SET status = 'failed', stage = 'interrupted',
                        error_category = 'interrupted',
                        error_message = '服务重启，验证已中断',
                        suggestion = '请重新发起验证', completed_at = ?
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, data_json,
                        created_at
                    ) VALUES (?, 'failed', 'interrupted',
                              '服务重启，验证已中断', '{}', ?)
                    """,
                    (row["id"], now),
                )

    def run_validation(self, run_id: str) -> None:
        run = self.get_validation_run(run_id)
        if run is None or run["status"] != "queued":
            return
        if not self._start_validation_run(run_id):
            return
        run = self.get_validation_run(run_id) or run
        config = self.get_version(
            str(run["config_version_id"]),
            include_secret=True,
        )
        if config is None:
            self._finish_validation_run(
                run,
                "failed",
                "config_missing",
                "API 配置不存在",
                "请重新保存 API 接入配置",
            )
            return
        for index, item in enumerate(run["items"]):
            self._update_validation_item(
                run_id,
                index,
                {
                    "status": "running",
                    "stage": "preparing",
                    "message": "正在检查模型与连接配置",
                    "started_at": utc_now(),
                },
                "model_started",
                "正在检查模型与连接配置",
            )

            def on_stage(
                stage: str,
                message: str,
                data: dict[str, Any],
                item_index: int = index,
            ) -> None:
                self._update_validation_item(
                    run_id,
                    item_index,
                    {"stage": stage, "message": message, **data},
                    "stage",
                    message,
                    data,
                )

            started = time.monotonic()
            try:
                report = self.model_probe.test(
                    config,
                    str(item["model_key"]),
                    str(item["effort"]),
                    on_stage=on_stage,
                )
            except Exception as exc:
                error = self._as_validation_error(exc)
                duration_ms = round((time.monotonic() - started) * 1000)
                model = self.model_catalog.get(str(item["model_id"]))
                if model:
                    self.model_catalog.set_validation(
                        model,
                        "failed",
                        str(error)[:500],
                        str(run["created_by"]),
                    )
                self._update_validation_item(
                    run_id,
                    index,
                    {
                        "status": "failed",
                        "stage": "failed",
                        "message": str(error),
                        "duration_ms": duration_ms,
                        "http_status": error.http_status,
                        "error_category": error.category,
                        "suggestion": error.suggestion,
                        "completed_at": utc_now(),
                    },
                    "model_failed",
                    str(error),
                    {
                        "duration_ms": duration_ms,
                        "http_status": error.http_status,
                        "error_category": error.category,
                        "suggestion": error.suggestion,
                    },
                )
                self._skip_validation_items(run_id, index + 1)
                if run["kind"] == "config":
                    self._set_config_validation(
                        str(run["target_id"]),
                        "failed",
                        str(error)[:500],
                        str(run["created_by"]),
                    )
                self._finish_validation_run(
                    run,
                    "failed",
                    error.category,
                    str(error),
                    error.suggestion,
                )
                return
            model = self.model_catalog.get(str(item["model_id"]))
            message = (
                f"HTTP {report['http_status']} · {report['duration_ms']} ms · "
                f"使用 {item['effort']} 推理强度测试通过"
            )
            if model:
                self.model_catalog.set_validation(
                    model,
                    "validated",
                    message,
                    str(run["created_by"]),
                )
            self._update_validation_item(
                run_id,
                index,
                {
                    "status": "passed",
                    "stage": "passed",
                    "message": "模型响应与结构检查通过",
                    "duration_ms": report["duration_ms"],
                    "http_status": report["http_status"],
                    "response_model": report["response_model"],
                    "completed_at": utc_now(),
                },
                "model_passed",
                "模型响应与结构检查通过",
                report,
            )
        if run["kind"] == "config":
            self._set_config_validation(
                str(run["target_id"]),
                "validated",
                f"连接与 {len(run['items'])} 个模型均测试通过",
                str(run["created_by"]),
            )
        self._finish_validation_run(
            run,
            "passed",
            None,
            "全部模型验证通过",
            None,
        )

    @staticmethod
    def _validation_item(
        model: dict[str, Any],
        effort: str,
        role: str,
    ) -> dict[str, Any]:
        return {
            "model_id": model["id"],
            "model_key": model["model_key"],
            "display_name": model["display_name"],
            "effort": effort,
            "role": role,
            "status": "pending",
            "stage": "queued",
            "message": "等待验证",
            "duration_ms": None,
            "http_status": None,
            "response_model": None,
            "error_category": None,
            "suggestion": None,
            "started_at": None,
            "completed_at": None,
        }

    def _create_validation_run(
        self,
        kind: str,
        target_id: str,
        connection_id: str,
        config_version_id: str,
        actor_id: str,
        config: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now()
        run_id = new_id("validation")
        with self.database.transaction(immediate=True) as connection:
            active = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE kind = ? AND target_id = ?
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (kind, target_id),
            ).fetchone()
            if active:
                run_id = str(active["id"])
            else:
                connection.execute(
                    """
                    INSERT INTO api_validation_runs(
                        id, kind, target_id, connection_id,
                        config_version_id, status, stage, endpoint,
                        timeout_seconds, items_json, total_count,
                        created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        kind,
                        target_id,
                        connection_id,
                        config_version_id,
                        f"{str(config['base_url']).rstrip('/')}/responses",
                        int(config["timeout_seconds"]),
                        json.dumps(items, ensure_ascii=False),
                        len(items),
                        actor_id,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, data_json,
                        created_at
                    ) VALUES (?, 'queued', 'queued', '验证已进入队列', ?, ?)
                    """,
                    (
                        run_id,
                        json.dumps(
                            {"kind": kind, "total_count": len(items)},
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
        return self.get_validation_run(run_id) or {}

    def _start_validation_run(self, run_id: str) -> bool:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            updated = connection.execute(
                """
                UPDATE api_validation_runs
                SET status = 'running', stage = 'preparing', started_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, run_id),
            )
            if updated.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, data_json,
                    created_at
                ) VALUES (?, 'started', 'preparing',
                          '开始执行真实模型验证', '{}', ?)
                """,
                (run_id, now),
            )
        return True

    def _update_validation_item(
        self,
        run_id: str,
        index: int,
        changes: dict[str, Any],
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT items_json FROM api_validation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            items = json.loads(row["items_json"])
            items[index].update(changes)
            completed_count = sum(
                item["status"] in {"passed", "failed"} for item in items
            )
            connection.execute(
                """
                UPDATE api_validation_runs
                SET items_json = ?, stage = ?, completed_count = ?
                WHERE id = ?
                """,
                (
                    json.dumps(items, ensure_ascii=False),
                    str(items[index]["stage"]),
                    completed_count,
                    run_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, model_key,
                    data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_type,
                    str(items[index]["stage"]),
                    message,
                    str(items[index]["model_key"]),
                    json.dumps(data or {}, ensure_ascii=False),
                    now,
                ),
            )

    def _skip_validation_items(self, run_id: str, start_index: int) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT items_json FROM api_validation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            items = json.loads(row["items_json"])
            for item in items[start_index:]:
                item.update(
                    {
                        "status": "skipped",
                        "stage": "skipped",
                        "message": "前序模型验证失败，已停止后续验证",
                    }
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, model_key,
                        data_json, created_at
                    ) VALUES (?, 'model_skipped', 'skipped', ?, ?, '{}', ?)
                    """,
                    (
                        run_id,
                        item["message"],
                        item["model_key"],
                        now,
                    ),
                )
            connection.execute(
                "UPDATE api_validation_runs SET items_json = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), run_id),
            )

    def _finish_validation_run(
        self,
        run: dict[str, Any],
        status: str,
        error_category: str | None,
        message: str,
        suggestion: str | None,
    ) -> None:
        now = utc_now()
        stage = "passed" if status == "passed" else "failed"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE api_validation_runs
                SET status = ?, stage = ?, error_category = ?,
                    error_message = ?, suggestion = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    stage,
                    error_category,
                    None if status == "passed" else message,
                    suggestion,
                    now,
                    run["id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, data_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    "completed" if status == "passed" else "failed",
                    stage,
                    message,
                    json.dumps(
                        {
                            "error_category": error_category,
                            "suggestion": suggestion,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )

    def _set_config_validation(
        self,
        version_id: str,
        status: str,
        message: str,
        actor_id: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_config_versions
                SET validation_status = ?, validation_message = ?,
                    validated_at = ?
                WHERE id = ?
                """,
                (status, message, now, version_id),
            )
        add_audit(
            self.database,
            "api_config_version",
            version_id,
            "validate",
            actor_id,
            after={"status": status, "message": message},
        )

    @staticmethod
    def _as_validation_error(exc: Exception) -> ModelValidationError:
        if isinstance(exc, ModelValidationError):
            return exc
        return ModelValidationError(
            str(exc)[:500] or "模型验证失败",
            "unknown",
            "请检查模型配置后重新验证",
        )

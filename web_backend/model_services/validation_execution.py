from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from web_backend.model_catalog import ModelCatalogService
from web_backend.model_probe import ModelProbe, ModelValidationError
from web_backend.model_services.validation_events import (
    _ValidationItemEvent,
    _ValidationRunEvents,
)
from web_backend.model_services.validation_records import _ValidationRunRecords
from web_backend.security import utc_now


@dataclass(frozen=True)
class _ValidationRunContext:
    run: dict[str, Any]
    config: dict[str, Any]


class _ValidationRunExecution(_ValidationRunRecords, _ValidationRunEvents):
    """按顺序探测模型，首个失败后停止并记录完整执行结果。"""

    model_catalog: ModelCatalogService
    model_probe: ModelProbe
    get_version: Callable[..., dict[str, Any] | None]

    def run_validation(self, run_id: str) -> None:
        context = self._prepare_validation_context(run_id)
        if context is None:
            return
        for index, item in enumerate(context.run["items"]):
            error = self._run_validation_item(context, index, item)
            if error is not None:
                self._finish_failed_validation(context, index, error)
                return
        self._finish_successful_validation(context)

    def _prepare_validation_context(
        self,
        run_id: str,
    ) -> _ValidationRunContext | None:
        run = self.get_validation_run(run_id)
        if run is None or run["status"] != "queued":
            return None
        if not self._start_validation_run(run_id):
            return None
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
            return None
        return _ValidationRunContext(run=run, config=config)

    def _run_validation_item(
        self,
        context: _ValidationRunContext,
        index: int,
        item: dict[str, Any],
    ) -> ModelValidationError | None:
        run = context.run
        run_id = str(run["id"])
        self._update_validation_item(
            run_id,
            index,
            {
                "status": "running",
                "stage": "preparing",
                "message": "正在检查模型与连接配置",
                "started_at": utc_now(),
            },
            _ValidationItemEvent(
                event_type="model_started",
                message="正在检查模型与连接配置",
            ),
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
                _ValidationItemEvent(event_type="stage", message=message, data=data),
            )

        started = time.monotonic()
        try:
            report = self.model_probe.test(
                context.config,
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
                _ValidationItemEvent(
                    event_type="model_failed",
                    message=str(error),
                    data={
                        "duration_ms": duration_ms,
                        "http_status": error.http_status,
                        "error_category": error.category,
                        "suggestion": error.suggestion,
                    },
                ),
            )
            return error
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
            _ValidationItemEvent(
                event_type="model_passed",
                message="模型响应与结构检查通过",
                data=report,
            ),
        )
        return None

    def _finish_failed_validation(
        self,
        context: _ValidationRunContext,
        failed_index: int,
        error: ModelValidationError,
    ) -> None:
        run = context.run
        self._skip_validation_items(str(run["id"]), failed_index + 1)
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

    def _finish_successful_validation(
        self,
        context: _ValidationRunContext,
    ) -> None:
        run = context.run
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
    def _as_validation_error(exc: Exception) -> ModelValidationError:
        if isinstance(exc, ModelValidationError):
            return exc
        return ModelValidationError(
            str(exc)[:500] or "模型验证失败",
            "unknown",
            "请检查模型配置后重新验证",
        )

from __future__ import annotations

import builtins
from concurrent.futures import Future
from threading import Lock
from typing import Any

from web_backend.dashboard_common import (
    PAGE_SIZE_DEFAULT,
)
from web_backend.dashboard_insights import (
    InsightOptions,
    build_evidence_page,
    build_insights,
    build_report_diagnostics,
)
from web_backend.dashboard_issue_cases import list_issue_cases
from web_backend.dashboard_quality import (
    build_review_bias,
    build_summary,
    build_text_quality,
    list_sources,
)
from web_backend.dashboard_queries import build_drilldown, list_records
from web_backend.database import Database


class _DashboardAnalysis:
    database: Database
    _insights_lock: Lock
    _inflight_insights: dict[
        tuple[str, str, InsightOptions, str], Future[dict[str, Any]]
    ]

    def summary(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_summary(self.database, dashboard_id, version_id)

    def review_bias(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_review_bias(self.database, dashboard_id, version_id)

    def text_quality(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_text_quality(self.database, dashboard_id, version_id)

    def sources(
        self, dashboard_id: str, version_id: str
    ) -> builtins.list[dict[str, Any]]:
        return list_sources(self.database, dashboard_id, version_id)

    def insights(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        problem: str | None = None,
        subject: str | None = None,
        label_group: str | None = None,
        listing: str | None = None,
        product_name: str | None = None,
        product_sku: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        report_mode: bool = False,
        part: str = "full",
    ) -> dict[str, Any]:
        options = InsightOptions(
            problem=problem,
            subject=subject,
            label_group=label_group,
            listing=listing,
            product_name=product_name,
            product_sku=product_sku,
            date_from=date_from,
            date_to=date_to,
            report_mode=report_mode,
        )
        key = (dashboard_id, version_id, options, part)
        with self._insights_lock:
            future = self._inflight_insights.get(key)
            leader = future is None
            if future is None:
                future = Future()
                self._inflight_insights[key] = future
        if leader:
            try:
                if part == "full":
                    result = build_insights(
                        self.database, dashboard_id, version_id, options
                    )
                else:
                    result = build_insights(
                        self.database, dashboard_id, version_id, options, part=part
                    )
                future.set_result(result)
            except BaseException as exc:
                future.set_exception(exc)
            finally:
                with self._insights_lock:
                    del self._inflight_insights[key]
        return dict(future.result())

    def evidence_page(
        self,
        dashboard_id: str,
        version_id: str,
        options: InsightOptions,
        *,
        page: int = 1,
    ) -> dict[str, Any]:
        return build_evidence_page(
            self.database, dashboard_id, version_id, options, page=page
        )

    def report_diagnostics(
        self, dashboard_id: str, version_id: str, reason_codes: builtins.list[str]
    ) -> builtins.list[dict[str, Any]]:
        if not reason_codes:
            return []
        return build_report_diagnostics(
            self.database, dashboard_id, version_id, reason_codes
        )

    def issue_cases(
        self,
        dashboard_id: str,
        version_id: str,
        reason_codes: builtins.list[str],
        *,
        max_cases_per_reason: int = 3,
    ) -> builtins.list[dict[str, Any]]:
        return list_issue_cases(
            self.database,
            dashboard_id,
            version_id,
            reason_codes,
            max_cases_per_reason=max_cases_per_reason,
        )

    def records(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        return list_records(
            self.database,
            dashboard_id,
            version_id,
            page=page,
            page_size=page_size,
            **filters,
        )

    def drilldown(
        self,
        dashboard_id: str,
        version_id: str,
        group_by: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        return build_drilldown(
            self.database,
            dashboard_id,
            version_id,
            group_by,
            page=page,
            page_size=page_size,
            **filters,
        )

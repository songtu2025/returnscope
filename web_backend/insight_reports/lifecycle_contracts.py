from dataclasses import dataclass

GENERATION_ERROR_MESSAGE = (
    "报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。"
)


class InsightReportNotFound(ValueError):
    pass


class InsightReportConflict(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class _ReportCreationTarget:
    dashboard_id: str
    dashboard_version_id: str
    parent_job_id: str | None = None

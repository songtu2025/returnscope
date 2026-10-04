from __future__ import annotations

import argparse
import getpass
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from scripts.smoke_web_production import SmokeClient, validate_base_url


@dataclass(frozen=True)
class BusinessScope:
    """指定已发布的合成验收对象，不扫描或创建生产业务数据。"""

    result_version_id: str
    review_batch_id: str
    dashboard_id: str
    dashboard_version_id: str
    report_id: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _get(client: SmokeClient, path: str) -> dict[str, Any]:
    status, _headers, value = client.json(path)
    if status != 200 or not isinstance(value, dict):
        raise RuntimeError("业务接口未返回有效对象")
    return value


def _check_result(client: SmokeClient, scope: BusinessScope) -> dict[str, Any]:
    path = f"/api/classification-results/{quote(scope.result_version_id, safe='')}"
    result = _get(client, path)
    records = _get(client, path + "/records?page_size=1")
    summary = _get(client, path + "/summary")
    _require(
        result.get("version_id") == scope.result_version_id
        and result.get("publish_status") == "published"
        and result.get("source_review_batch_id") == scope.review_batch_id
        and bool(result.get("parent_version_id")),
        "分类结果不是指定复核批次发布的派生版本",
    )
    count = result.get("record_count")
    _require(
        isinstance(count, int)
        and count > 0
        and records.get("total") == count
        and summary.get("version_id") == scope.result_version_id
        and summary.get("metrics", {}).get("source_record_count") == count,
        "分类结果详情、分页和统计不一致或验收数据为空",
    )
    items = records.get("items", [])
    _require(
        bool(items)
        and all(
            item.get("result_version_id") == scope.result_version_id for item in items
        ),
        "分类记录所属版本不一致",
    )
    print("[通过] 分类结果版本、分页与统计")
    return result


def _check_review(
    client: SmokeClient, scope: BusinessScope, result: dict[str, Any]
) -> None:
    batch = _get(client, f"/api/review-batches/{quote(scope.review_batch_id, safe='')}")
    _require(
        batch.get("id") == scope.review_batch_id
        and batch.get("status") == "published"
        and batch.get("published_version_id") == scope.result_version_id
        and batch.get("base_result_version_id") == result["parent_version_id"]
        and batch.get("remaining_count") == 0,
        "复核批次状态或基础、派生版本关联不一致",
    )
    print("[通过] 人工复核批次与派生版本")


def _check_dashboard(
    client: SmokeClient, scope: BusinessScope, result: dict[str, Any]
) -> None:
    path = f"/api/analysis-dashboards/{quote(scope.dashboard_id, safe='')}"
    version_path = path + f"/versions/{quote(scope.dashboard_version_id, safe='')}"
    dashboard = _get(
        client, path + f"?version_id={quote(scope.dashboard_version_id, safe='')}"
    )
    version = dashboard.get("version", {})
    _require(
        dashboard.get("id") == scope.dashboard_id
        and version.get("version_id") == scope.dashboard_version_id,
        "驾驶舱返回了错误版本",
    )
    _require(
        [item.get("result_version_id") for item in version.get("source_snapshot", [])]
        == [scope.result_version_id]
        and not version.get("filters"),
        "验收驾驶舱必须只引用指定结果且不设置业务筛选",
    )
    status, _headers, sources = client.json(version_path + "/sources")
    _require(
        status == 200
        and isinstance(sources, list)
        and [item.get("result_version_id") for item in sources]
        == [scope.result_version_id],
        "驾驶舱来源接口与版本快照不一致",
    )
    summary = _get(client, version_path + "/summary")
    records = _get(client, version_path + "/records?page_size=1")
    _check_dashboard_counts(scope, result, version, summary, records)
    print("[通过] 驾驶舱版本、来源与统计")


def _check_dashboard_counts(
    scope: BusinessScope,
    result: dict[str, Any],
    version: dict[str, Any],
    summary: dict[str, Any],
    records: dict[str, Any],
) -> None:
    snapshot = version.get("summary", {})
    count = summary.get("record_count")
    basis = summary.get("counting_basis", "source_record")
    # 驾驶舱按反馈组计数，明细分页仍按原始行计数；分别核对相同口径。
    _require(
        summary.get("dashboard_id") == scope.dashboard_id
        and summary.get("version_id") == scope.dashboard_version_id
        and isinstance(count, int)
        and 0 < count <= result["record_count"]
        and count == snapshot.get("record_count")
        and basis == snapshot.get("counting_basis", "source_record")
        and basis in {"source_record", "feedback_group"}
        and (basis == "feedback_group" or count == result["record_count"])
        and records.get("total") == result["record_count"],
        "驾驶舱统计快照、计数口径或明细来源不一致",
    )


def _check_report(client: SmokeClient, scope: BusinessScope) -> None:
    report = _get(client, f"/api/ai-insight-reports/{quote(scope.report_id, safe='')}")
    _require(
        report.get("id") == scope.report_id
        and report.get("status") == "completed"
        and report.get("dashboard_id") == scope.dashboard_id
        and report.get("dashboard_version_id") == scope.dashboard_version_id,
        "报告尚未完成或引用了错误的驾驶舱版本",
    )
    source = report.get("evidence", {}).get("source", {})
    _require(
        source.get("dashboard_id") == scope.dashboard_id
        and source.get("dashboard_version_id") == scope.dashboard_version_id,
        "报告证据与驾驶舱版本不一致",
    )
    print("[通过] 报告状态与证据版本")


def check_business(client: SmokeClient, scope: BusinessScope) -> None:
    """只读核对单来源、无筛选的合成验收链路。"""
    try:
        result = _check_result(client, scope)
        _check_review(client, scope, result)
        _check_dashboard(client, scope, result)
        _check_report(client, scope)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise RuntimeError("业务接口字段不完整或格式不正确") from None


def run_smoke(base_url: str, email: str, password: str, scope: BusinessScope) -> None:
    client = SmokeClient(base_url)
    try:
        client.login(email, password)
        print("[通过] 登录与安全会话")
        check_business(client, scope)
    finally:
        client.logout()
    print("[通过] 退出登录")


def main() -> None:
    parser = argparse.ArgumentParser(description="只读验收指定合成对象的业务关联")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--allow-http", action="store_true")
    names = (
        "result_version_id",
        "review_batch_id",
        "dashboard_id",
        "dashboard_version_id",
        "report_id",
    )
    for name in names:
        parser.add_argument("--" + name.replace("_", "-"), required=True)
    args = parser.parse_args()
    try:
        base_url = validate_base_url(args.base_url, args.allow_http)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    scope = BusinessScope(**{name: getattr(args, name) for name in names})
    password = os.getenv("WEBAPP_SMOKE_PASSWORD") or getpass.getpass("测试账号密码：")
    try:
        run_smoke(base_url, args.email.strip().lower(), password, scope)
    except RuntimeError as exc:
        raise SystemExit(f"[失败] {exc}") from None
    print("业务关联验收通过")


if __name__ == "__main__":
    main()

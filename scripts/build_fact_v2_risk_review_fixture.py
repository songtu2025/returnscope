"""将 fact_v2 风险样本转换为分类标准验证使用的 Review Excel。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook

REVIEW_SHEET_NAME = "Review样本"
REFERENCE_SHEET_NAME = "人工参考答案"
REVIEW_HEADERS = (
    "评论编号",
    "评论标题",
    "评论内容",
    "一级品类",
    "下单店铺",
    "ASIN",
)
REFERENCE_HEADERS = (
    "评论编号",
    "标签编码",
    "评价方向",
    "部位",
    "证据",
    "事实状态",
    "使用者",
    "商品对象",
    "条件",
)
DEFAULT_CATEGORY = "手套"
DEFAULT_STORE = "FACT_V2_RISK"
NO_LABEL = "无标签"


def load_contract(path: Path) -> dict[str, Any]:
    """读取并校验转换所需的最小风险样本结构。"""
    contract = json.loads(path.read_text(encoding="utf-8"))
    cases = contract.get("cases") if isinstance(contract, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("风险样本必须包含非空 cases 列表")

    seen_case_ids: set[str] = set()
    for position, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"第 {position} 个案例必须是对象")
        case_id = str(case.get("case_id") or "").strip()
        comment = str(case.get("comment") or "").strip()
        risk_type = str(case.get("risk_type") or "").strip()
        facts = case.get("expected_facts")
        if not case_id or not comment or not risk_type:
            raise ValueError(f"第 {position} 个案例缺少 case_id、comment 或 risk_type")
        if case_id in seen_case_ids:
            raise ValueError(f"case_id 重复：{case_id}")
        if not isinstance(facts, list) or not facts:
            raise ValueError(f"案例 {case_id} 必须包含非空 expected_facts 列表")
        seen_case_ids.add(case_id)
        for fact_position, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                raise ValueError(
                    f"案例 {case_id} 的第 {fact_position} 个事实必须是对象"
                )
            for field in ("sentiment", "statement_type", "evidence", "product_ref"):
                if not str(fact.get(field) or "").strip():
                    raise ValueError(
                        f"案例 {case_id} 的第 {fact_position} 个事实缺少 {field}"
                    )
            evidence = str(fact["evidence"]).strip()
            if evidence not in comment:
                raise ValueError(f"案例 {case_id} 的证据不在评论原文中：{evidence}")
    return contract


def build_workbook(contract: dict[str, Any]) -> Workbook:
    """按现有验证服务字段约定构造 Review 工作簿。"""
    workbook = Workbook()
    review_sheet = workbook.active
    review_sheet.title = REVIEW_SHEET_NAME
    review_sheet.append(REVIEW_HEADERS)

    reference_sheet = workbook.create_sheet(REFERENCE_SHEET_NAME)
    reference_sheet.append(REFERENCE_HEADERS)

    for case in contract["cases"]:
        case_id = str(case["case_id"]).strip()
        review_sheet.append(
            (
                case_id,
                "",
                str(case["comment"]).strip(),
                DEFAULT_CATEGORY,
                DEFAULT_STORE,
                str(case["risk_type"]).strip(),
            )
        )
        for fact in case["expected_facts"]:
            reference_sheet.append(
                (
                    case_id,
                    str(fact.get("required_label_code") or NO_LABEL).strip(),
                    str(fact["sentiment"]).strip(),
                    str(fact.get("part") or "UNSPECIFIED").strip(),
                    str(fact["evidence"]).strip(),
                    str(fact["statement_type"]).strip(),
                    str(fact.get("actor_ref") or "").strip(),
                    str(fact["product_ref"]).strip(),
                    str(fact.get("condition") or "").strip(),
                )
            )
    return workbook


def convert_fixture(input_path: Path, output_path: Path) -> None:
    """转换风险样本并写入用户指定的 xlsx 路径。"""
    if output_path.suffix.lower() != ".xlsx":
        raise ValueError("输出文件必须使用 .xlsx 扩展名")
    contract = load_contract(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_workbook(contract)
    try:
        workbook.save(output_path)
    finally:
        workbook.close()


def build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="将 fact_v2 风险样本 JSON 转换为 Review 验证 Excel。"
    )
    parser.add_argument("input", type=Path, help="风险样本 JSON 路径")
    parser.add_argument("output", type=Path, help="目标 Review Excel 路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行命令行转换。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        convert_fixture(args.input, args.output)
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"转换失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""为结果下载设置可筛选、可追溯的阅读布局。"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any
from unicodedata import east_asian_width

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from web_backend.classification_results.result_export import (
    SEMANTIC_COLUMNS,
    SOURCE_COLUMNS,
    SUMMARY_COLUMNS,
)

_WIDTHS = {
    "反馈编号": 16,
    "订单号": 24,
    "产品名称": 28,
    "反馈正文": 54,
    "反馈标题 / 原因": 28,
    "中文语义": 42,
    "分类路径": 46,
    "原文证据": 48,
    "判断说明": 42,
    "修正时间": 27,
    "源记录编号": 36,
}


def result_workbook(
    summaries: list[dict[str, Any]],
    semantics: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    for title, columns, rows in (
        ("反馈汇总", SUMMARY_COLUMNS, summaries),
        ("语义明细", SEMANTIC_COLUMNS, semantics),
        ("源明细", SOURCE_COLUMNS, sources),
    ):
        sheet = workbook.create_sheet(title)
        sheet.append(columns)
        sheet.freeze_panes = "D2" if title == "反馈汇总" else "C2"
        sheet.sheet_view.showGridLines = False
        sheet.sheet_view.zoomScale = 85
        sheet.row_dimensions[1].height = 32
        for index, name in enumerate(columns, 1):
            sheet.column_dimensions[get_column_letter(index)].width = _WIDTHS.get(
                name, 20
            )
        for row in rows:
            sheet.append([row.get(name) for name in columns])
        for row in sheet:
            for cell in row:
                # 反馈正文和标识均为数据，不能让以等号开头的内容变成公式。
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                cell.font = Font(name="微软雅黑", size=11, color="153D34")
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if cell.row == 1:
                    cell.fill = PatternFill("solid", fgColor="176C57")
                    cell.font = Font(
                        name="微软雅黑", size=11, bold=True, color="FFFFFF"
                    )
                elif cell.row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="F0F7F4")
            if row[0].row > 1:
                lines = max(
                    _display_lines(
                        cell.value, _WIDTHS.get(columns[cell.column - 1], 20)
                    )
                    for cell in row
                )
                sheet.row_dimensions[row[0].row].height = min(
                    max(lines * 16 + 10, 42), 180
                )
        sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _display_lines(value: Any, width: int) -> int:
    return sum(
        max(
            1,
            math.ceil(
                sum(2 if east_asian_width(c) in "WF" else 1 for c in line) / width
            ),
        )
        for line in str(value or "").split("\n")
    )

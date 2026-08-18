from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from return_semantics.data import load_return_dataset
from return_semantics.sampling import build_gold_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 SK001 金标准标注样本")
    parser.add_argument(
        "--returns",
        type=Path,
        default=PROJECT_ROOT / "input_data" / "SEEKWAY_US_.csv",
    )
    parser.add_argument(
        "--products",
        type=Path,
        default=PROJECT_ROOT / "input_data" / "产品信息_20231103.xlsx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "output" / "SK001_金标准标注样本.xlsx",
    )
    parser.add_argument("--total", type=int, default=500)
    parser.add_argument("--calibration-size", type=int, default=300)
    return parser.parse_args()


def write_sample(sample: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        sample.to_excel(writer, sheet_name="人工标注", index=False)
        sheet = writer.book["人工标注"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 28

        header_fill = PatternFill("solid", fgColor="D9EAF7")
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        widths = {
            "A": 20,
            "B": 16,
            "C": 16,
            "D": 26,
            "E": 80,
            "F": 14,
            "G": 35,
            "H": 35,
            "I": 35,
            "J": 24,
            "K": 60,
            "L": 18,
            "M": 50,
        }
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width

        validation = DataValidation(
            type="list",
            formula1='"是,否"',
            allow_blank=True,
        )
        sheet.add_data_validation(validation)
        validation.add(f"L2:L{len(sample) + 1}")


def main() -> None:
    args = parse_args()
    dataset = load_return_dataset(
        args.returns,
        args.products,
        store="SEEKWAY:US",
        listing="SK001",
    )
    sample = build_gold_sample(
        dataset.unique_comments,
        total=args.total,
        calibration_size=args.calibration_size,
    )
    write_sample(sample, args.output)
    print(f"已生成: {args.output}")
    print(f"样本数: {len(sample)}")
    print(sample["数据用途"].value_counts().to_dict())
    print(sample["抽样类型"].value_counts().to_dict())


if __name__ == "__main__":
    main()

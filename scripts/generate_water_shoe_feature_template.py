from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.water_shoe_workbook import build_workbook, verify_workbook


class _SkuAggregate(TypedDict):
    canonical_sku: str
    asins: set[str]
    fnskus: set[str]
    titles: set[str]
    aliases: set[str]
    latest_date: str
    latest_title: str
    record_count: int


SOURCE_HEADERS = {
    "return-date",
    "sku",
    "asin",
    "fnsku",
    "product-name",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成涉水鞋 SKU 产品特征模板")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("input_data") / "SEEKWAY_US_.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("input_data") / "涉水鞋_SKU产品特征模板.xlsx",
    )
    return parser.parse_args()


def is_placeholder_sku(sku: str) -> bool:
    return sku.startswith("Amazon.Found.")


def build_asin_sku_map(source_path: Path) -> dict[str, str]:
    asin_to_skus: dict[str, set[str]] = defaultdict(set)

    with source_path.open("r", encoding="cp1252", newline="") as source_file:
        reader = csv.DictReader(source_file)
        missing_headers = SOURCE_HEADERS.difference(reader.fieldnames or [])
        if missing_headers:
            missing_text = ", ".join(sorted(missing_headers))
            raise ValueError(f"退货报告缺少字段: {missing_text}")

        for row in reader:
            sku = row["sku"].strip()
            asin = row["asin"].strip()
            if not is_placeholder_sku(sku):
                asin_to_skus[asin].add(sku)

    invalid = {
        asin: sorted(skus) for asin, skus in asin_to_skus.items() if len(skus) != 1
    }
    if invalid:
        raise ValueError(f"ASIN 无法唯一映射规范 SKU: {invalid}")

    return {asin: next(iter(skus)) for asin, skus in asin_to_skus.items()}


def aggregate_skus(
    source_path: Path,
    asin_sku_map: dict[str, str],
) -> list[dict[str, object]]:
    aggregates: dict[str, _SkuAggregate] = {}

    with source_path.open("r", encoding="cp1252", newline="") as source_file:
        reader = csv.DictReader(source_file)
        for row in reader:
            raw_sku = row["sku"].strip()
            asin = row["asin"].strip()
            canonical_sku = asin_sku_map.get(asin)
            if canonical_sku is None:
                raise ValueError(f"ASIN 没有规范 SKU: {asin}")
            if not is_placeholder_sku(raw_sku) and raw_sku != canonical_sku:
                raise ValueError(f"SKU 与 ASIN 映射冲突: {raw_sku}, {asin}")

            item = aggregates.setdefault(
                canonical_sku,
                {
                    "canonical_sku": canonical_sku,
                    "asins": set(),
                    "fnskus": set(),
                    "titles": set(),
                    "aliases": set(),
                    "latest_date": "",
                    "latest_title": "",
                    "record_count": 0,
                },
            )
            item["asins"].add(asin)
            item["record_count"] += 1

            if is_placeholder_sku(raw_sku):
                expected_alias = f"Amazon.Found.{asin}"
                if raw_sku != expected_alias:
                    raise ValueError(f"占位 SKU 与 ASIN 不一致: {raw_sku}, {asin}")
                item["aliases"].add(raw_sku)
                continue

            fnsku = row["fnsku"].strip()
            if fnsku and fnsku != asin:
                item["fnskus"].add(fnsku)

            title = row["product-name"].strip()
            if title:
                item["titles"].add(title)
                return_date = row["return-date"].strip()
                if return_date >= item["latest_date"]:
                    item["latest_date"] = return_date
                    item["latest_title"] = title

    output_rows = [_sku_output_row(sku, item) for sku, item in aggregates.items()]
    return sorted(output_rows, key=lambda row: str(row["canonical_sku"]).lower())


def _sku_output_row(canonical_sku: str, item: _SkuAggregate) -> dict[str, object]:
    if len(item["asins"]) != 1:
        raise ValueError(f"规范 SKU 对应多个 ASIN: {canonical_sku}")
    if len(item["fnskus"]) != 1:
        raise ValueError(f"规范 SKU 无法唯一确定参考 FNSKU: {canonical_sku}")
    if not item["latest_title"]:
        raise ValueError(f"规范 SKU 缺少可识别标题: {canonical_sku}")

    return {
        "canonical_sku": canonical_sku,
        "asin": next(iter(item["asins"])),
        "reference_fnsku": next(iter(item["fnskus"])),
        "product_name_latest_observed": item["latest_title"],
        "product_name_version_count": len(item["titles"]),
        "source_sku_aliases": " | ".join(sorted(item["aliases"])),
        "return_record_count_raw": item["record_count"],
        "category_id": "water_shoes",
    }


def main() -> None:
    args = parse_args()
    asin_sku_map = build_asin_sku_map(args.source)
    rows = aggregate_skus(args.source, asin_sku_map)
    build_workbook(rows, args.output)
    verify_workbook(args.output, expected_rows=len(rows))
    print(f"已生成: {args.output}")
    print(f"规范 SKU 数: {len(rows)}")


if __name__ == "__main__":
    main()

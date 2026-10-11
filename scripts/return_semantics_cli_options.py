from __future__ import annotations

import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行涉水鞋退货语义分析批处理")
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
        "--store",
        required=True,
        help="产品信息表中的店铺/站点",
    )
    parser.add_argument(
        "--listing",
        help="可选 Listing；不指定时处理店铺全部 Listing",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="分类标准数据库；默认使用 Web 应用数据库",
    )
    standard_source = parser.add_mutually_exclusive_group()
    standard_source.add_argument(
        "--standard-id",
        default="classification_standard_footwear",
        help="使用该分类标准的当前发布版本",
    )
    standard_source.add_argument(
        "--standard-version-id",
        help="使用指定的不可变分类标准版本",
    )
    parser.add_argument(
        "--claims",
        type=Path,
        help="可选 Listing 声明配置；仅在指定 --listing 时使用",
    )
    parser.add_argument(
        "--dotenv",
        type=Path,
        default=PROJECT_ROOT / ".env",
    )
    parser.add_argument(
        "--model-config-source",
        choices=("web", "env"),
        default="web",
        help="模型配置来源；默认复用 Web 用户偏好，env 仅用于显式调试",
    )
    parser.add_argument(
        "--model-preference-user-id",
        help="Web 模型偏好所属用户；仅存在多个用户偏好时必须指定",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        help="模型缓存路径；未指定时根据处理范围生成",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="结果文件路径；未指定时根据处理范围生成",
    )
    parser.add_argument(
        "--secondary-model",
        help="二次审核模型；未指定时使用提供商默认配置",
    )
    parser.add_argument("--skip-secondary", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not args.store.strip():
        raise ValueError("--store 不能为空")
    if args.claims is not None and not (args.listing or "").strip():
        raise ValueError("--claims 必须与 --listing 同时使用")
    if args.offset < 0:
        raise ValueError("--offset 不能小于 0")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")


def build_scope_slug(store: str, listing: str | None) -> str:
    scope = f"{store}_{listing}" if listing else store
    return re.sub(r"[^A-Za-z0-9._-]+", "_", scope).strip("_").lower()

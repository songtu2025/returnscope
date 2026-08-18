from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from return_semantics.data import load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.model_client import JsonlCache, create_model_client
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import ListingClaimsConfig
from return_semantics.taxonomy import (
    load_listing_claims,
    load_taxonomy,
    validate_taxonomy_claims,
)


def parse_args() -> argparse.Namespace:
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
        "--taxonomy",
        type=Path,
        default=PROJECT_ROOT / "config" / "taxonomy_water_shoes.json",
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
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if not args.store.strip():
        raise ValueError("--store 不能为空")
    if args.claims is not None and not (args.listing or "").strip():
        raise ValueError("--claims 必须与 --listing 同时使用")
    if args.offset < 0:
        raise ValueError("--offset 不能小于 0")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")


def print_progress(current: int, total: int) -> None:
    if current == total or current % 10 == 0:
        print(f"分类进度: {current}/{total}")


def build_scope_slug(store: str, listing: str | None) -> str:
    scope = f"{store}_{listing}" if listing else store
    return re.sub(r"[^A-Za-z0-9._-]+", "_", scope).strip("_").lower()


def main() -> None:
    args = parse_args()
    validate_args(args)
    store = args.store.strip()
    listing = (args.listing or "").strip() or None
    scope_slug = build_scope_slug(store, listing)
    cache_path = args.cache or (
        PROJECT_ROOT / "cache" / f"{scope_slug}_model_responses.jsonl"
    )
    output_path = args.output or (
        PROJECT_ROOT / "output" / f"{scope_slug}_退货语义分类结果.xlsx"
    )

    taxonomy = load_taxonomy(args.taxonomy)
    if args.claims is None:
        claims = ListingClaimsConfig(
            version=f"{scope_slug}-no-claims-v1",
            claims=[],
        )
    else:
        claims = load_listing_claims(args.claims)
        validate_taxonomy_claims(taxonomy, claims)
    dataset = load_return_dataset(
        args.returns,
        args.products,
        store=store,
        listing=listing,
    )

    scope_name = f"{store} / {listing}" if listing else f"{store} 全部 Listing"
    print(f"{scope_name} MSKU 数: {len(dataset.mskus)}")
    print(f"退货记录数: {len(dataset.records)}")
    print(f"有效评论数: {int(dataset.records['has_text_evidence'].sum())}")
    print(f"去重评论组合数: {len(dataset.unique_comments)}")
    if args.dry_run:
        return

    client = create_model_client(args.dotenv)
    cache = JsonlCache(cache_path)
    secondary_model = None
    if not args.skip_secondary:
        secondary_model = args.secondary_model or client.settings.secondary_model
    print(f"模型提供商: {client.settings.provider}")
    print(f"主模型: {client.settings.model}")
    print(f"二次审核模型: {secondary_model or '未启用'}")
    cheap_model = getattr(client.settings, "cheap_model", None)
    print(f"低成本模型: {cheap_model or '未启用'}")
    print(f"并发工作线程: {client.settings.max_workers}")
    run = classify_comments(
        unique_comments=dataset.unique_comments,
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=cache,
        offset=args.offset,
        limit=args.limit,
        force=args.force,
        secondary_model=secondary_model,
        progress=print_progress,
    )
    export_results(
        output_path=output_path,
        dataset=dataset,
        results=run.classifications,
        taxonomy=taxonomy,
    )

    print(f"各模型调用数: {run.model_calls_by_model}")
    print(f"各模型缓存命中数: {run.cache_hits_by_model}")
    print(f"模型路由: {run.routing}")
    print(f"请求指标: {run.request_metrics}")
    print(f"各模型 Token 用量: {run.usage_by_model}")
    statuses = Counter(result.status.value for result in run.classifications.values())
    print(f"模型调用数: {run.model_calls}")
    print(f"缓存命中数: {run.cache_hits}")
    print(f"处理状态: {dict(statuses)}")
    print(f"Token 用量: {run.usage}")
    print(f"已输出: {output_path}")


if __name__ == "__main__":
    main()

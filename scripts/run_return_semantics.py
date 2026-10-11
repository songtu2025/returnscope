from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from return_semantics.data import load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.model_client import (
    JsonlCache,
)
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import ListingClaimsConfig
from return_semantics.taxonomy import (
    load_listing_claims,
    validate_taxonomy_claims,
)
from scripts.return_semantics_cli_options import (
    build_scope_slug,
    parse_args,
    validate_args,
)
from scripts.return_semantics_cli_runtime import (
    build_model_runtime,
    load_standard_taxonomy,
    resolve_database_path,
)


def print_progress(current: int, total: int) -> None:
    if current == total or current % 10 == 0:
        print(f"分类进度: {current}/{total}")


def main() -> None:
    args = parse_args()
    validate_args(args)
    database_path = resolve_database_path(args.database, args.dotenv)
    store = args.store.strip()
    listing = (args.listing or "").strip() or None
    scope_slug = build_scope_slug(store, listing)
    cache_path = args.cache or (
        PROJECT_ROOT / "cache" / f"{scope_slug}_model_responses.jsonl"
    )
    output_path = args.output or (
        PROJECT_ROOT / "output" / f"{scope_slug}_退货语义分类结果.xlsx"
    )

    taxonomy, standard_version = load_standard_taxonomy(
        database_path,
        args.standard_id,
        args.standard_version_id,
    )
    print(
        f"分类标准: {standard_version['standard_name']} "
        f"V{standard_version['version_no']} ({standard_version['id']})"
    )
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

    client, model_policy = build_model_runtime(
        database_path=database_path,
        dotenv_path=args.dotenv,
        source=args.model_config_source,
        user_id=args.model_preference_user_id,
        standard_version=standard_version,
        secondary_model=args.secondary_model,
    )
    cache = JsonlCache(cache_path)
    secondary_model = None
    if not args.skip_secondary:
        review = model_policy["actual"].get("review")
        secondary_model = str(review["model"]) if review else None
    print(f"模型配置来源: {args.model_config_source}")
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
        model_policy_version=str(model_policy["version"]),
        secondary_is_fallback=bool(
            model_policy["actual"].get("review")
            and model_policy["actual"]["review"].get("fallback_from") == "secondary"
        ),
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

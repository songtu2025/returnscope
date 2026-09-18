from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from return_semantics.capabilities import resolve_model_policy
from return_semantics.data import load_return_dataset
from return_semantics.exporter import export_results
from return_semantics.model_client import (
    JsonlCache,
    Sub2APIClient,
    create_model_client,
    load_dotenv,
)
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import ListingClaimsConfig, TaxonomyConfig
from return_semantics.taxonomy import (
    load_listing_claims,
    validate_taxonomy_claims,
)
from web_backend.agent_runner import AgentRunner
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
    ClassificationStandardService,
)
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.model_preference_service import ModelPreferenceService
from web_backend.security import SecretBox
from web_backend.settings import Settings


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


def print_progress(current: int, total: int) -> None:
    if current == total or current % 10 == 0:
        print(f"分类进度: {current}/{total}")


def build_scope_slug(store: str, listing: str | None) -> str:
    scope = f"{store}_{listing}" if listing else store
    return re.sub(r"[^A-Za-z0-9._-]+", "_", scope).strip("_").lower()


def load_standard_taxonomy(
    database_path: Path,
    standard_id: str,
    standard_version_id: str | None,
) -> tuple[TaxonomyConfig, dict[str, object]]:
    database = Database(database_path)
    database.initialize()
    service = ClassificationStandardService(database)
    if standard_version_id:
        version = service.get_version(standard_version_id)
        if version["status"] != "published":
            raise ClassificationStandardNotFound("分类标准版本尚未发布")
    else:
        version = service.current_version_for_standard(standard_id)
    taxonomy = service.taxonomy_for_version(str(version["id"]))
    return taxonomy, version


def resolve_database_path(database_path: Path | None, dotenv_path: Path) -> Path:
    load_dotenv(dotenv_path)
    return (database_path or Settings.from_env().database_path).resolve()


def _model_config(settings: Any) -> dict[str, Any]:
    return {
        "primary_model": settings.model,
        "primary_effort": settings.reasoning_effort,
        "cheap_model": settings.cheap_model,
        "cheap_effort": settings.cheap_reasoning_effort,
        "secondary_model": settings.secondary_model,
        "secondary_effort": settings.secondary_reasoning_effort,
    }


def _web_model_preference(
    database: Database,
    user_id: str | None,
) -> dict[str, Any]:
    preferences = ModelPreferenceService(database)
    if user_id:
        preference = preferences.task_policy(user_id)
        if preference is None:
            raise ValueError("指定用户尚未配置 Web 模型偏好")
        return preference
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT user_id FROM user_model_preferences ORDER BY updated_at DESC"
        ).fetchall()
    if not rows:
        raise ValueError(
            "尚未配置 Web 模型偏好；请先在 Web 中配置，或显式使用 "
            "--model-config-source env"
        )
    if len(rows) > 1:
        raise ValueError("存在多个 Web 模型偏好，请指定 --model-preference-user-id")
    preference = preferences.task_policy(str(rows[0]["user_id"]))
    if preference is None:
        raise ValueError("Web 模型偏好不可用")
    return preference


def build_model_runtime(
    *,
    database_path: Path,
    dotenv_path: Path,
    source: str,
    user_id: str | None,
    standard_version: dict[str, Any],
    secondary_model: str | None,
) -> tuple[Sub2APIClient, dict[str, Any]]:
    capability = ClassificationStandardService._capability_from_snapshot(
        standard_version["snapshot"]
    )
    if source == "env":
        print("警告: 当前显式使用环境变量模型配置，不与 Web 用户偏好联动")
        base_settings = create_model_client(dotenv_path).settings
        config = _model_config(base_settings)
    else:
        app_settings = Settings.from_env()
        database = Database(database_path)
        preference = _web_model_preference(database, user_id)
        config_service = ConfigService(
            database,
            SecretBox(app_settings.encryption_key),
        )
        base_settings = config_service.build_model_settings(
            str(preference["config_version_id"])
        )
        config = preference
    if secondary_model:
        config = {**config, "secondary_model": secondary_model}
    model_policy = resolve_model_policy(capability, config)
    effective_settings = AgentRunner._settings_for_model_policy(
        base_settings,
        model_policy,
    )
    return Sub2APIClient(effective_settings), model_policy


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
            and model_policy["actual"]["review"].get("fallback_from")
            == "secondary"
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

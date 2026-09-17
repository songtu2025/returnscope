import json
import sys
from pathlib import Path
from typing import Annotated, cast

from fastapi import Cookie, FastAPI

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _SchemaOnlyResultService:
    """只为路由工厂提供类型占位，不执行任何服务调用。"""


class _SchemaOnlyStandardService:
    """只为路由工厂提供类型占位，不执行任何服务调用。"""


def build_openapi_schema() -> dict[str, object]:
    """构造仅包含分类结果路由的确定性 OpenAPI schema。"""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from web_backend.classification_result_service import (
        ClassificationResultService,
    )
    from web_backend.classification_standard_service import (
        ClassificationStandardService,
    )
    from web_backend.routers.accounts import SESSION_COOKIE
    from web_backend.routers.classification_results import (
        create_classification_result_router,
    )

    def current_user(
        session_token: Annotated[
            str | None,
            Cookie(alias=SESSION_COOKIE),
        ] = None,
    ) -> dict[str, str]:
        """仅提供生产鉴权依赖签名；生成 OpenAPI 时不会执行。"""
        del session_token
        return {"id": "schema-only"}

    result_service = cast(
        ClassificationResultService,
        _SchemaOnlyResultService(),
    )
    standard_service = cast(
        ClassificationStandardService,
        _SchemaOnlyStandardService(),
    )
    app = FastAPI(
        title="Classification Results API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )
    app.include_router(
        create_classification_result_router(
            result_service,
            current_user,
            standard_service,
        )
    )
    return cast(dict[str, object], app.openapi())


def main() -> int:
    schema = build_openapi_schema()
    sys.stdout.write(
        json.dumps(
            schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

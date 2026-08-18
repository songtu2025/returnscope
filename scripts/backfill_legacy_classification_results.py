from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="预览或回填历史 Listing 分类结果到不可变结果池",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行回填；默认仅预览",
    )
    parser.add_argument(
        "--preview-hash",
        default="",
        help="执行回填时必须提供最近一次预览返回的 preview_hash",
    )
    return parser.parse_args()


def main() -> int:
    from web_backend.agent_runner import AgentRunner
    from web_backend.classification_result_service import ClassificationResultService
    from web_backend.database import Database
    from web_backend.legacy_result_backfill_service import (
        LegacyResultBackfillService,
    )
    from web_backend.settings import Settings

    args = parse_args()
    try:
        settings = Settings.from_env()
        database = Database(settings.database_path)
        result_service = ClassificationResultService(database)
        runner = AgentRunner(database, settings, object(), result_service)
        service = LegacyResultBackfillService(database, runner)
        output = (
            service.apply(args.preview_hash)
            if args.apply
            else service.preview()
        )
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"error": str(exc)[:500]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

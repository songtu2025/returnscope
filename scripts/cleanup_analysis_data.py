"""预览全部历史分析业务的清理范围；执行必须另行获得线上操作授权。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="预览或清理全部历史分析业务；保留商品、账号配置、标准规则与项目备份"
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--all-analysis",
        action="store_true",
        required=True,
        help="明确选择全部历史分析业务范围",
    )
    parser.add_argument("--apply", action="store_true", help="执行清理；默认只读预览")
    parser.add_argument("--preview-hash", default="")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--actor-id", default="")
    parser.add_argument("--app-stopped", action="store_true")
    return parser.parse_args()


def main() -> int:
    from web_backend.analysis_cleanup import (
        CleanupApproval,
        apply_cleanup,
        preview_cleanup,
    )

    args = parse_args()
    try:
        if args.apply:
            if args.backup is None:
                raise ValueError("执行前必须提供已经校验的完整备份")
            output = apply_cleanup(
                args.database,
                args.data_dir,
                approval=CleanupApproval(
                    args.preview_hash, args.backup, args.actor_id, args.app_stopped
                ),
            )
        else:
            output = preview_cleanup(args.database, args.data_dir).summary()
        print(json.dumps(output, ensure_ascii=False))
        return 0 if output.get("complete", True) else 2
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

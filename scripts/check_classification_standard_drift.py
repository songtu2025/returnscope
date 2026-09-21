from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from web_backend.classification_standard_drift import compare_published_standards

    parser = argparse.ArgumentParser(description="检查分类标准运行配置漂移")
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "runtime" / "app.db",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=PROJECT_ROOT / "config" / "category_capabilities.json",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    comparisons = compare_published_standards(
        args.database.resolve(),
        args.registry.resolve(),
    )
    if args.as_json:
        print(
            json.dumps(
                [comparison.as_dict() for comparison in comparisons],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        impact_labels = {
            "none": "一致",
            "metadata": "元数据漂移",
            "behavioral": "行为漂移",
            "missing": "配置缺失",
        }
        for comparison in comparisons:
            marker = impact_labels[comparison.impact]
            print(
                f"[{marker}] {comparison.standard_key}: "
                f"仓库={comparison.seed_taxonomy_version or '-'} "
                f"({comparison.seed_recognition_profile or '-'})，"
                f"已发布={comparison.published_taxonomy_version or '-'} "
                f"({comparison.published_recognition_profile or '-'})"
            )
            print(
                "  运行绑定: "
                f"版本={comparison.published_version_id or '-'}，"
                f"仓库指纹={comparison.seed_hash[:12] if comparison.seed_hash else '-'}，"
                "发布指纹="
                f"{comparison.published_hash[:12] if comparison.published_hash else '-'}"
            )
            for source_name, identity in (
                ("仓库种子", comparison.seed_identity),
                ("生产发布", comparison.published_identity),
            ):
                if identity is None:
                    continue
                print(
                    f"  {source_name}: 逻辑={identity.logic_version}，"
                    f"策略={identity.model_policy_version} "
                    f"({identity.first_pass_role}/{identity.review_role or '-'}), "
                    f"标签={identity.label_count}，品类={identity.category_count}"
                )
            if comparison.differences:
                print(f"  差异字段：{', '.join(comparison.differences)}")
    return int(any(item.status != "match" for item in comparisons))


if __name__ == "__main__":
    raise SystemExit(main())

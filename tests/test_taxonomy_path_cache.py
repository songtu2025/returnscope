"""验证导出阶段分类路径复用的生命周期和并发隔离。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from threading import Barrier

import pytest
from test_classification_result_download import context as context
from test_classification_result_workbook import assert_workbook_members_equal
from test_taxonomy_hierarchy import tree_payload as tree_payload

from return_semantics import taxonomy_hierarchy as hierarchy
from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy import load_taxonomy
from web_backend import classification_result_download as download


@pytest.mark.parametrize("legacy", [False, True])
def test_paths_are_copied_and_context_restores_after_nested_failure(
    tree_payload, legacy
):
    taxonomy = (
        load_taxonomy(Path("config/taxonomy_eyewear.json"))
        if legacy
        else TaxonomyConfig.model_validate(tree_payload)
    )
    code = taxonomy.labels[0].code
    names = hierarchy.label_path(taxonomy, code)
    codes = hierarchy.label_path_codes(taxonomy, code)
    other = taxonomy.model_copy(deep=True)
    other.labels[0].name = "另一个标准名称"
    with hierarchy.reuse_taxonomy_paths(taxonomy):
        hierarchy.label_path(taxonomy, code).append("不能污染缓存")
        hierarchy.label_path_codes(taxonomy, code).clear()
        assert hierarchy.label_path(taxonomy, code) == names
        assert hierarchy.label_path_codes(taxonomy, code) == codes
        assert hierarchy.label_path(taxonomy, "missing") == []
        assert hierarchy.label_path_codes(taxonomy, "missing") == []
        assert hierarchy.label_path(other, code)[-1] == "另一个标准名称"
        with pytest.raises(RuntimeError), hierarchy.reuse_taxonomy_paths(other):
            assert hierarchy.label_path(other, code)[-1] == "另一个标准名称"
            raise RuntimeError("合成异常")
        assert hierarchy.label_path(taxonomy, code) == names
    taxonomy.labels[0].name = "更新后的标准名称"
    assert hierarchy.label_path(taxonomy, code)[-1] == "更新后的标准名称"
    with hierarchy.reuse_taxonomy_paths(taxonomy):
        assert hierarchy.label_path(taxonomy, code)[-1] == "更新后的标准名称"


@pytest.mark.parametrize("mode", ["threads", "async"])
def test_parallel_exports_have_independent_path_caches(tree_payload, monkeypatch, mode):
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    calls = []
    original = hierarchy._category_chain

    def counted(categories, code):
        calls.append(code)
        return original(categories, code)

    monkeypatch.setattr(hierarchy, "_category_chain", counted)
    expected = ["FUNCTION", "WARMTH", "COLD"]
    if mode == "threads":
        barrier = Barrier(2)

        def run_thread(_):
            with hierarchy.reuse_taxonomy_paths(taxonomy):
                first = hierarchy.label_path_codes(taxonomy, "COLD")
                barrier.wait(timeout=5)
                assert hierarchy.label_path_codes(taxonomy, "COLD") == first
                return first

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(run_thread, range(2))) == [expected, expected]
    else:

        async def run_async():
            with hierarchy.reuse_taxonomy_paths(taxonomy):
                first = hierarchy.label_path_codes(taxonomy, "COLD")
                await asyncio.sleep(0)
                assert hierarchy.label_path_codes(taxonomy, "COLD") == first
                return first

        async def run_all():
            return await asyncio.gather(run_async(), run_async())

        assert asyncio.run(run_all()) == [expected, expected]
    assert len(calls) == 2
    hierarchy.label_path_codes(taxonomy, "COLD")
    hierarchy.label_path_codes(taxonomy, "COLD")
    assert len(calls) == 4


def test_export_path_cache_preserves_all_workbook_members(context, monkeypatch):
    snapshot = context.service.capture_export([context.version["version_id"]])
    cached = context.service.snapshot_workbook(snapshot)
    monkeypatch.setattr(download, "reuse_taxonomy_paths", nullcontext)
    uncached = context.service.snapshot_workbook(snapshot)
    assert_workbook_members_equal(cached, uncached)

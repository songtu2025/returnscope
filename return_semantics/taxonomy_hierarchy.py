from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from return_semantics.schemas import CategoryDefinition, TaxonomyConfig


def _category_chain(
    categories: dict[str, CategoryDefinition], code: str | None
) -> list[str]:
    chain: list[str] = []
    while code is not None:
        if code not in categories:
            raise ValueError(f"分类父节点不存在: {code}")
        if code in chain:
            raise ValueError(f"分类节点存在循环关系: {code}")
        chain.append(code)
        code = categories[code].parent_code
    return list(reversed(chain))


def validate_hierarchy(taxonomy: TaxonomyConfig) -> None:
    """校验树关系，并由根节点统一派生旧查询使用的分组。"""
    nodes = [*taxonomy.categories, *taxonomy.labels]
    codes = [node.code for node in nodes]
    if any(not code.strip() for code in codes) or len(set(codes)) != len(codes):
        raise ValueError("分类和标签编码必须非空且全树唯一")
    if any(not node.name.strip() for node in nodes):
        raise ValueError("分类和标签名称不能为空")
    categories = {node.code: node for node in taxonomy.categories}
    for category in taxonomy.categories:
        _category_chain(categories, category.code)
    for label in taxonomy.labels:
        if label.parent_code is None:
            raise ValueError(f"末端标签必须指定分类父节点: {label.code}")
        chain = _category_chain(categories, label.parent_code)
        label.group = categories[chain[0]].name


def label_path_codes(taxonomy: TaxonomyConfig, code: str) -> list[str]:
    """返回分类或标签的完整编码路径，未知编码返回空列表。"""
    categories = {node.code: node for node in taxonomy.categories}
    if taxonomy.structure_version == 2 and code in categories:
        return _category_chain(categories, code)
    label = next((label for label in taxonomy.labels if label.code == code), None)
    if label is None:
        return []
    if taxonomy.structure_version == 1:
        return [code]
    return [*_category_chain(categories, label.parent_code), code]


def label_path(taxonomy: TaxonomyConfig, code: str) -> list[str]:
    """依据当前版本还原名称路径，旧版本只保留原有分组信息。"""
    if taxonomy.structure_version == 2:
        names = {
            node.code: node.name for node in [*taxonomy.categories, *taxonomy.labels]
        }
        return [names[node_code] for node_code in label_path_codes(taxonomy, code)]
    label = next((label for label in taxonomy.labels if label.code == code), None)
    if label is None:
        return []
    return [label.group, label.name] if label.group else [label.name]


def descendant_label_codes(taxonomy: TaxonomyConfig, category_code: str) -> list[str]:
    """返回分类下的全部末端编码，旧版本允许按原分组名称查询。"""
    if taxonomy.structure_version == 1:
        return [label.code for label in taxonomy.labels if label.group == category_code]
    return [
        label.code
        for label in taxonomy.labels
        if category_code in label_path_codes(taxonomy, label.code)[:-1]
    ]

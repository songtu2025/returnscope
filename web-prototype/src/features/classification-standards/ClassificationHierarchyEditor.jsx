import { useState } from "react";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { labelChanges } from "./labelDraftPolicy";

export function ClassificationHierarchyChanges({ content, baseContent }) {
  const changes = labelChanges(
    content.categories ?? [],
    baseContent?.categories ?? [],
  ).filter((entry) => entry.status !== "未修改");
  if (!changes.length) return null;
  return (
    <section className="taxonomy-import-paths" aria-label="分类层级变更">
      <b>分类层级变更</b>
      {changes.map((entry) => (
        <p key={entry.label.code}>
          {entry.status === "拟停用" ? "删除" : entry.status}：
          {entry.before && `${taxonomyPath(baseContent, entry.before).join(" → ")} → `}
          {entry.status === "拟停用"
            ? "移除分类"
            : taxonomyPath(content, entry.label).join(" → ")}
        </p>
      ))}
    </section>
  );
}

export function ClassificationHierarchyEditor({ content, onChange, disabled }) {
  const [selected, setSelected] = useState("");
  const categories = content.categories ?? [];
  const current = categories.find((item) => item.code === selected);
  const update = (items) => {
    const next = { ...content, categories: items };
    onChange({
      ...next,
      labels: next.labels.map((label) => ({
        ...label,
        group: taxonomyPath(next, label)[0] || "",
      })),
    });
  };
  const descendants = new Set(current ? [current.code] : []);
  for (let index = 0; index < categories.length; index += 1)
    for (const item of categories)
      if (descendants.has(item.parent_code)) descendants.add(item.code);
  const hasChildren =
    current &&
    [...categories, ...content.labels].some(
      (item) => item.parent_code === current.code,
    );
  const add = () => {
    const used = new Set([...categories, ...content.labels].map((item) => item.code));
    let index = 1;
    while (used.has(`CATEGORY_${index}`)) index += 1;
    const code = `CATEGORY_${index}`;
    update([...categories, { code, name: "新分类", parent_code: selected || null }]);
    setSelected(code);
  };
  return (
    <details className="standard-editor-section hierarchy-category-editor">
      <summary>维护分类层级（{categories.length} 个分类节点）</summary>
      <fieldset disabled={disabled}>
        <label>
          选择分类
          <select
            aria-label="选择分类节点"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">根级（用于新增一级分类）</option>
            {categories.map((item) => (
              <option key={item.code} value={item.code}>
                {taxonomyPath(content, item).join(" → ")}
              </option>
            ))}
          </select>
        </label>
        {current && (
          <>
            <label>
              分类名称
              <input
                aria-label="分类名称"
                value={current.name}
                onChange={(event) =>
                  update(
                    categories.map((item) =>
                      item.code === selected
                        ? { ...item, name: event.target.value }
                        : item,
                    ),
                  )
                }
              />
            </label>
            <label>
              上级分类
              <select
                aria-label="分类的上级"
                value={current.parent_code || ""}
                onChange={(event) =>
                  update(
                    categories.map((item) =>
                      item.code === selected
                        ? { ...item, parent_code: event.target.value || null }
                        : item,
                    ),
                  )
                }
              >
                <option value="">无（一级分类）</option>
                {categories
                  .filter((item) => !descendants.has(item.code))
                  .map((item) => (
                    <option key={item.code} value={item.code}>
                      {taxonomyPath(content, item).join(" → ")}
                    </option>
                  ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={hasChildren}
              onClick={() => {
                update(categories.filter((item) => item.code !== selected));
                setSelected("");
              }}
            >
              删除分类
            </button>
            {hasChildren && <small>请先移动或移除该分类下的子分类和标签。</small>}
          </>
        )}
        <button type="button" className="secondary-button" onClick={add}>
          {current ? "新增下级分类" : "新增一级分类"}
        </button>
      </fieldset>
    </details>
  );
}

export function ClassificationHierarchyDirectory({ content, entries, renderLabel }) {
  const categories = content.categories ?? [];
  const renderBranch = (category) => {
    const children = categories.filter((item) => item.parent_code === category.code);
    const labels = entries.filter((item) => item.label.parent_code === category.code);
    return (
      <details key={category.code} open className="hierarchy-directory-branch">
        <summary>{category.name}</summary>
        {children.map(renderBranch)}
        {labels.map(renderLabel)}
      </details>
    );
  };
  const categoryCodes = new Set(categories.map((item) => item.code));
  return (
    <>
      {categories.filter((item) => !item.parent_code).map(renderBranch)}
      {entries
        .filter((item) => !categoryCodes.has(item.label.parent_code))
        .map(renderLabel)}
    </>
  );
}

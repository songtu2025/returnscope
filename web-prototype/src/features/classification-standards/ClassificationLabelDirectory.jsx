import { MagnifyingGlass, Plus } from "@phosphor-icons/react";
import Input from "antd/es/input";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { ClassificationHierarchyDirectory } from "./ClassificationHierarchyEditor";

export function ClassificationLabelDirectory({
  content,
  baseContent,
  matches,
  groups,
  query,
  group,
  selected,
  hierarchical,
  editable,
  busy,
  selectedRef,
  addLabelRef,
  onAdd,
  onSelect,
  onQueryChange,
  onGroupChange,
  onResetFilters,
}) {
  const renderLabel = (item) => {
    const value = item.index < 0 ? item.label.code : item.index;
    return (
      <button
        ref={selected === value ? selectedRef : undefined}
        key={item.index < 0 ? `removed-${item.label.code}` : item.index}
        type="button"
        aria-current={selected === value ? "true" : undefined}
        disabled={busy}
        onClick={() => onSelect(value)}
      >
        <span>
          <b>{item.label.name || "未命名标签"}</b>
          <small>
            {taxonomyPath(item.index < 0 ? baseContent : content, item.label)
              .slice(0, -1)
              .join(" → ") || "未分组"}
          </small>
        </span>
        {item.status !== "未修改" && (
          <span
            className={`label-change-badge ${item.status === "拟停用" ? "removed" : "changed"}`}
          >
            {item.status}
          </span>
        )}
      </button>
    );
  };

  return (
    <aside className="label-directory" aria-label="标签目录">
      <header>
        <strong>
          标签目录 <span>{content.labels.length}</span>
        </strong>
        {editable && (
          <button
            ref={addLabelRef}
            type="button"
            className="icon-button"
            aria-label="增加标签"
            disabled={busy}
            onClick={onAdd}
          >
            <Plus size={17} />
          </button>
        )}
      </header>
      <Input
        className="standard-search-box"
        type="search"
        aria-label="搜索标签"
        prefix={<MagnifyingGlass size={16} />}
        placeholder="搜索标签或别名"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
      />
      <select
        aria-label="筛选标签分组"
        value={group}
        onChange={(event) => onGroupChange(event.target.value)}
      >
        <option value="">全部分组</option>
        {groups.map((name) => (
          <option key={name}>{name}</option>
        ))}
      </select>
      <div className="label-directory-scroll">
        {hierarchical ? (
          <ClassificationHierarchyDirectory
            content={content}
            entries={matches}
            renderLabel={renderLabel}
          />
        ) : (
          matches.map(renderLabel)
        )}
        {!matches.length && (
          <p className="label-directory-empty">
            没有匹配的标签。
            <button type="button" onClick={onResetFilters}>
              重置筛选
            </button>
          </p>
        )}
      </div>
    </aside>
  );
}

import { useEffect, useMemo, useRef } from "react";
import { CaretRight } from "@phosphor-icons/react";
import "../../styles/analysis-dashboards/hierarchy.css";

/** @typedef {import("./analysisDashboardContracts").InsightHierarchyNode} InsightHierarchyNode */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {{hierarchy: InsightHierarchyNode[], selectedCode: string, pendingReason?: string, reasonStatus?: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} HierarchyProps */
/** @typedef {{children: Map<string, InsightHierarchyNode[]>, ancestors: Set<string>}} HierarchyView */

/** @param {InsightHierarchyNode[]} hierarchy @param {string} selectedCode @returns {HierarchyView} */
function hierarchyView(hierarchy, selectedCode) {
  const nodes = new Map(hierarchy.map((node) => [node.value, node]));
  const children = /** @type {Map<string, InsightHierarchyNode[]>} */ (new Map());
  // 数据已包含祖先；只重排父子关系，不在前端重新统计数量。
  for (const node of [...hierarchy].sort(
    (left, right) =>
      right.record_count - left.record_count || left.value.localeCompare(right.value),
  )) {
    const parent = node.parent_code || "";
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent)?.push(node);
  }
  const ancestors = /** @type {Set<string>} */ (new Set());
  let parent = nodes.get(selectedCode)?.parent_code;
  while (parent) {
    ancestors.add(parent);
    parent = nodes.get(parent)?.parent_code;
  }
  return { children, ancestors };
}

/** @param {HierarchyProps & {node: InsightHierarchyNode, view: HierarchyView}} props */
function HierarchyNode(props) {
  const { node, view, selectedCode, pendingReason, reasonStatus, onUpdateRoute } =
    props;
  const branchRef = useRef(/** @type {HTMLDetailsElement | null} */ (null));
  const children = view.children.get(node.value) || [];
  useEffect(() => {
    // 新选中原因时展开祖先；用户随后手动收起不会被普通重绘覆盖。
    if (view.ancestors.has(node.value) && branchRef.current) {
      branchRef.current.open = true;
    }
  }, [selectedCode, node.value, view.ancestors]);
  const caption = (
    <>
      <span>{node.label_name}</span>{" "}
      <strong>
        {pendingReason === node.value
          ? reasonStatus
          : `${Number(node.record_count).toLocaleString()}条`}
      </strong>
    </>
  );
  return (
    <li>
      {children.length ? (
        <details ref={branchRef} className="return-hierarchy-branch">
          <summary>
            <CaretRight size={14} aria-hidden="true" />
            {caption}
          </summary>
          <ul>
            {children.map((child) => (
              <HierarchyNode key={child.value} {...props} node={child} />
            ))}
          </ul>
        </details>
      ) : (
        <button
          type="button"
          className={selectedCode === node.value ? "active" : ""}
          aria-current={selectedCode === node.value ? "true" : undefined}
          onClick={() =>
            onUpdateRoute({ problem: node.value, recordPage: 1, reasonPage: 0 })
          }
        >
          {caption}
        </button>
      )}
    </li>
  );
}

/** @param {HTMLDivElement | null} container */
function revealSelection(container) {
  const selected = container?.querySelector('[aria-current="true"]');
  if (!container || !selected) return;
  const bounds = container.getBoundingClientRect();
  const item = selected.getBoundingClientRect();
  // 只滚动树容器，避免自动定位把整个页面拉走。
  if (item.top < bounds.top) container.scrollTop += item.top - bounds.top;
  else if (item.bottom > bounds.bottom)
    container.scrollTop += item.bottom - bounds.bottom;
}

/** @param {HierarchyProps} props */
export function ReturnReasonExplorerHierarchy(props) {
  const { hierarchy, selectedCode } = props;
  const rootRef = useRef(/** @type {HTMLDetailsElement | null} */ (null));
  const containerRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const view = useMemo(
    () => hierarchyView(hierarchy, selectedCode),
    [hierarchy, selectedCode],
  );
  useEffect(() => {
    if (rootRef.current?.open) revealSelection(containerRef.current);
  }, [selectedCode]);
  if (!hierarchy.length) return null;
  return (
    <details
      ref={rootRef}
      className="return-hierarchy-explorer"
      onToggle={(event) => {
        if (event.currentTarget.open) revealSelection(containerRef.current);
      }}
    >
      <summary>
        <CaretRight size={16} aria-hidden="true" />
        <span>按分类层级查看</span>
        <small>{hierarchy.length}项</small>
      </summary>
      <p>父级按评论去重；选择具体原因查看诊断</p>
      <div ref={containerRef} className="return-hierarchy-scroll">
        <ul aria-label="分类层级">
          {(view.children.get("") || []).map((node) => (
            <HierarchyNode key={node.value} {...props} node={node} view={view} />
          ))}
        </ul>
      </div>
    </details>
  );
}

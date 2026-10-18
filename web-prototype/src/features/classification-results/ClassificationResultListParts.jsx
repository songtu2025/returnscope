import Button from "antd/es/button";
import Checkbox from "antd/es/checkbox";
import { ResultPoolActions } from "./ResultPoolActions";
import { formatTime } from "../../lib/presentation";
import { resultActionPolicy } from "./resultActionPolicy";
import { buildHash, navigateHash, parseHash } from "../../app/hashRouter";
import {
  classificationResultPoolQuery,
  classificationResultRouteState,
} from "./classificationResultRoute";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse & { product_name?: string | null }} ClassificationResultVersion
 * @typedef {{
 *   result_version_id: string,
 *   store_site: string,
 *   listing: string,
 *   record_count: number,
 *   unit_count: number
 * }} SelectedResult
 */

/** @param {ClassificationResultVersion} result @returns {string[]} */
function productNames(result) {
  const names = Array.isArray(result.product_names)
    ? result.product_names.filter(Boolean)
    : result.product_name
      ? [result.product_name]
      : [];
  return names;
}

/**
 * @typedef {{
 *   result: ClassificationResultVersion,
 *   onOpen: () => void,
 *   onPrimary: () => void,
 *   selectable: boolean,
 *   selected: boolean,
 *   onToggle: () => void,
 *   onBeforeOpenSource?: () => void,
 *   onChanged?: () => void | Promise<void>
 * }} ResultPoolRowProps
 */
/** @param {ResultPoolRowProps} props */
export function ResultPoolRow({
  result,
  onOpen,
  onPrimary,
  selectable,
  selected,
  onToggle,
  onChanged,
  onBeforeOpenSource,
}) {
  const policy = resultActionPolicy(result);
  return (
    <article className={`result-pool-row ${selected ? "is-selected" : ""}`} role="row">
      <ResultPoolStatus
        result={result}
        policy={policy}
        selectable={selectable}
        selected={selected}
        onToggle={onToggle}
      />
      <ResultPoolMetadata
        result={result}
        onOpen={onOpen}
        onBeforeOpenSource={onBeforeOpenSource}
      />
      <ResultPoolActions
        result={result}
        onOpen={onOpen}
        onPrimary={onPrimary}
        onChanged={onChanged}
      />
    </article>
  );
}

/** @param {Pick<ResultPoolRowProps, "result" | "selectable" | "selected" | "onToggle"> & {policy: ReturnType<typeof resultActionPolicy>}} props */
function ResultPoolStatus({ result, policy, selectable, selected, onToggle }) {
  const disabledReason = policy.dashboardSelectable ? "" : policy.blockingReason;
  return (
    <>
      {selectable && (
        <div role="cell">
          <Checkbox
            className="result-selection-cell"
            title={disabledReason}
            aria-label={`选择 ${result.listing || "未提供 Listing"} 结果 v${result.version} · ${formatTime(result.published_at || result.created_at)} · ${result.version_id}`}
            checked={selected}
            disabled={Boolean(disabledReason)}
            onChange={onToggle}
          >
            {disabledReason && <small>{disabledReason}</small>}
          </Checkbox>
        </div>
      )}
      <div className="result-state-cell" role="cell">
        <span className={`result-quality-badge ${policy.state}`}>{policy.label}</span>
      </div>
    </>
  );
}

/** @param {Pick<ResultPoolRowProps, "result" | "onOpen" | "onBeforeOpenSource">} props */
function ResultPoolMetadata({ result, onOpen, onBeforeOpenSource }) {
  const names = productNames(result);
  return (
    <>
      <div className="result-listing-cell" role="cell">
        <button
          className="text-button result-listing-link"
          data-list-return-id={result.version_id}
          onClick={onOpen}
        >
          {result.listing || "未提供 Listing"}
        </button>
        <span>{result.store_site || "未提供店铺/站点"}</span>
        <small title={`结果版本 ID：${result.version_id}`}>
          结果 v{result.version} · {result.version_id.slice(-8)}
        </small>
        {result.source_task_id ? (
          <button
            className="text-button result-source-link"
            title={`查看来源任务：${result.source_task_id}`}
            data-list-return-id={`source:${result.version_id}`}
            onClick={() => {
              onBeforeOpenSource?.();
              navigateHash("analysis-tasks", {
                task_id: result.source_task_id,
                segment_id: result.source_segment_id,
                result_pool_return: buildHash(
                  "classification-results",
                  classificationResultPoolQuery(
                    classificationResultRouteState(parseHash().query),
                  ),
                ),
              });
            }}
          >
            来源任务 <code>{result.source_task_id}</code>
          </button>
        ) : (
          <small>来源任务未提供</small>
        )}
      </div>
      <div className="result-product-cell" role="cell">
        <b title={names.join("、")}>{names[0] || "未提供"}</b>
        {names.length > 1 && <span>另有 {names.length - 1} 个产品名称</span>}
      </div>
      <div className="result-scale-cell" role="cell">
        <b>{Number(result.record_count || 0).toLocaleString()} 条记录</b>
        <span>{Number(result.unit_count || 0).toLocaleString()} 个分类单元</span>
      </div>
      <div className="result-time-cell" role="cell">
        <b>{formatTime(result.published_at || result.created_at)}</b>
        <span>
          {result.standard_name || result.agent_family || "未提供分类标准"}
          {result.standard_version ? ` · V${result.standard_version}` : ""}
        </span>
      </div>
    </>
  );
}

/**
 * @param {{
 *   selected: SelectedResult[],
 *   currentPageIds: Set<string>,
 *   loading: boolean,
 *   onRemove: (id: string) => void,
 *   onClear: () => void
 * }} props
 */
export function DashboardSelectionBar({
  selected,
  currentPageIds,
  loading,
  onRemove,
  onClear,
}) {
  const listingCount = new Set(
    selected.map((item) => `${item.store_site}::${item.listing}`),
  ).size;
  const currentCount = selected.filter((item) =>
    currentPageIds.has(item.result_version_id),
  ).length;
  return (
    <aside className="dashboard-selection-bar" aria-label="看板数据选择">
      <div>
        <b>已选 {selected.length} 个结果版本</b>
        <span>覆盖 {listingCount} 个 Listing</span>
        <span>
          {loading
            ? "当前页统计更新中"
            : `当前页 ${currentCount} 个 · 其他页或筛选外 ${selected.length - currentCount} 个`}
        </span>
        <span>创建时包含全部已选结果</span>
      </div>
      <Button type="text" disabled={!selected.length} onClick={onClear}>
        清空
      </Button>
      <details className="result-selection-details">
        <summary>查看已选结果</summary>
        <ul>
          {selected.map((item) => (
            <li key={item.result_version_id}>
              <div>
                <b>
                  {item.listing || "未提供 Listing"} · {item.store_site || "未提供店铺"}
                </b>
                <code>{item.result_version_id}</code>
              </div>
              <Button
                type="text"
                onClick={() => onRemove(item.result_version_id)}
                aria-label={`取消选择结果 ${item.result_version_id}`}
              >
                取消选择
              </Button>
            </li>
          ))}
        </ul>
      </details>
    </aside>
  );
}

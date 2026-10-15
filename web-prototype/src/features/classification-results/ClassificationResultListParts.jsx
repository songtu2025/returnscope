import Button from "antd/es/button";
import Checkbox from "antd/es/checkbox";
import { ResultPoolActions } from "./ResultPoolActions";
import { formatTime } from "../../lib/presentation";
import { resultActionPolicy } from "./resultActionPolicy";

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
      <ResultPoolMetadata result={result} onOpen={onOpen} />
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
            aria-label={`选择 ${result.listing || "未提供 Listing"} 结果 v${result.version}`}
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

/** @param {Pick<ResultPoolRowProps, "result" | "onOpen">} props */
function ResultPoolMetadata({ result, onOpen }) {
  const names = productNames(result);
  return (
    <>
      <div className="result-listing-cell" role="cell">
        <button className="text-button result-listing-link" onClick={onOpen}>
          {result.listing || "未提供 Listing"}
        </button>
        <span>{result.store_site || "未提供店铺/站点"}</span>
        <small>结果 v{result.version}</small>
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
 *   onClear: () => void
 * }} props
 */
export function DashboardSelectionBar({ selected, onClear }) {
  const listingCount = new Set(
    selected.map((item) => `${item.store_site}::${item.listing}`),
  ).size;
  return (
    <aside className="dashboard-selection-bar" aria-label="看板数据选择">
      <div>
        <b>已选 {selected.length} 个结果版本</b>
        <span>覆盖 {listingCount} 个 Listing</span>
      </div>
      <Button type="text" disabled={!selected.length} onClick={onClear}>
        清空
      </Button>
    </aside>
  );
}

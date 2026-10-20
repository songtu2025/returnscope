import { ResultPoolStatus } from "./ResultPoolStatus";
import { Pagination } from "./ClassificationResultCommon";
import { ResultPoolRow } from "./ClassificationResultListParts";
import { isDashboardSelectable, resultVersionId } from "./resultActionPolicy";
import Checkbox from "antd/es/checkbox";
import { useRef } from "react";
import { useLoadingHeight } from "../../hooks/useLoadingHeight";

/** @typedef {import("./classificationResultListContracts").ResultPoolContext} ResultPoolContext */

/** @param {{items: import("./classificationResultListContracts").ClassificationResultVersion[], selectedIds: Set<string>, loading: boolean, error: string, onToggle: (items: import("./classificationResultListContracts").ClassificationResultVersion[]) => void}} props */
function ResultPageSelection({ items, selectedIds, loading, error, onToggle }) {
  const unavailable = loading || Boolean(error);
  const eligible = items.filter(isDashboardSelectable);
  const selectedCount = eligible.filter((result) =>
    selectedIds.has(resultVersionId(result)),
  ).length;
  return (
    <div className="result-page-selection">
      <Checkbox
        aria-label="选择当前页可选结果"
        title="仅选择当前页已发布且未删除的结果"
        checked={
          !unavailable && eligible.length > 0 && selectedCount === eligible.length
        }
        indeterminate={
          !unavailable && selectedCount > 0 && selectedCount < eligible.length
        }
        disabled={unavailable || !eligible.length}
        onChange={() => onToggle(eligible)}
      >
        {unavailable ? "选择当前页结果" : `选择当前页 ${eligible.length} 个可选结果`}
      </Checkbox>
      <span role="status">
        {loading
          ? "正在更新当前页范围…"
          : error
            ? "当前页范围读取失败"
            : `当前页已选 ${selectedCount} 个`}
      </span>
    </div>
  );
}

/** @param {ResultPoolContext & {rememberPosition?: (id: string) => void}} context */
export function ResultPoolContent(context) {
  const {
    route,
    updateRoute,
    selectedIds,
    toggleSelection,
    runPrimaryAction,
    data,
    loading,
    totalPages,
    changePage,
    changePageSize,
  } = context;
  const regionRef = useRef(/** @type {HTMLElement | null} */ (null));
  useLoadingHeight(loading, regionRef);
  return (
    <section
      ref={regionRef}
      className="result-pool-card loading-region"
      aria-busy={loading}
    >
      <ResultPoolStatus {...context} />{" "}
      {data && data.items.length > 0 && (
        <>
          <ResultPageSelection
            items={data.items}
            selectedIds={selectedIds}
            loading={loading}
            error={context.error}
            onToggle={context.toggleSelections}
          />
          <div
            className={`result-pool-table is-selecting ${route.lifecycle === "deleted" ? "is-deleted" : "is-current"}`}
            role="table"
            aria-label="分类结果"
            aria-busy={loading}
          >
            <div className="result-pool-head" role="row">
              <span role="columnheader">选择</span>
              <span role="columnheader">结果状态</span>
              <span role="columnheader">Listing / 店铺</span>
              <span role="columnheader">产品名称</span>
              <span role="columnheader">数据规模</span>
              <span role="columnheader">发布时间</span>
              <span role="columnheader">操作</span>
            </div>
            {data.items.map((result) => (
              <ResultPoolRow
                key={result.version_id}
                result={result}
                onChanged={context.load}
                selectable
                selected={selectedIds.has(resultVersionId(result))}
                onToggle={() => toggleSelection(result)}
                onPrimary={() => runPrimaryAction(result)}
                onBeforeOpenSource={() =>
                  context.rememberPosition?.(`source:${result.version_id}`)
                }
                onOpen={() => {
                  context.rememberPosition?.(result.version_id);
                  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
                  updateRoute({
                    version: result.version_id,
                    tab: "records",
                    recordPage: 1,
                    recordQualityStatus: route.qualityStatus,
                    commentStatus: "",
                    systemRerunRequired: "",
                    problem: "",
                    productName: "",
                    productSku: "",
                    orderId: "",
                    feedbackSourceRecordId: "",
                  });
                }}
              />
            ))}
          </div>
          <Pagination
            page={route.page}
            pageSize={route.pageSize}
            total={data.total}
            totalPages={totalPages}
            onPage={changePage}
            onPageSize={changePageSize}
          />
        </>
      )}
    </section>
  );
}

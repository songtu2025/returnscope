import { DrilldownColumn } from "./ClassificationResultDetailParts";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailDrilldown(context) {
  const { route, updateRoute, drilldowns, selectProductName, selectProductSku } =
    context;
  return (
    <section className="result-drilldown-card">
      <header>
        <div>
          <b>业务下钻</b>
          <span>问题 → Listing → 产品名称 → 产品SKU → order-id → 分类结果与证据</span>
        </div>
        {(route.problem || route.productName || route.productSku || route.orderId) && (
          <button
            className="text-button"
            onClick={() =>
              updateRoute({
                problem: "",
                productName: "",
                productSku: "",
                orderId: "",
                recordPage: 1,
              })
            }
          >
            清除下钻条件
          </button>
        )}
      </header>
      <div className="drilldown-columns">
        <ResultProblemDrilldown {...context} />
        <DrilldownColumn
          title="产品名称"
          items={drilldowns.product_name}
          selected={route.productName}
          emptyLabel="未提供"
          onSelect={selectProductName}
        />
        <DrilldownColumn
          title="产品SKU"
          items={drilldowns.product_sku}
          selected={route.productSku}
          emptyLabel="未提供"
          onSelect={selectProductSku}
        />
      </div>
    </section>
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultProblemDrilldown(context) {
  const {
    route,
    result,
    summary,
    drilldowns,
    reviewRecords,
    allNeedReviewWithoutProblems,
    selectProblem,
  } = context;
  const hierarchyProblems = summary?.hierarchy_problems ?? [];
  const hasHierarchy = hierarchyProblems.length > 0;
  return (
    <DrilldownColumn
      title={hasHierarchy ? "问题层级" : "问题"}
      items={hasHierarchy ? hierarchyProblems : drilldowns.problem}
      limit={hasHierarchy ? Infinity : 12}
      selected={route.problem}
      emptyTitle={allNeedReviewWithoutProblems ? "尚未形成问题标签" : "暂无数据"}
      emptyDescription={
        allNeedReviewWithoutProblems
          ? `当前 ${Number(
              reviewRecords || result.record_count,
            ).toLocaleString()} 条记录需复核，可在查看证据时人工修正。`
          : ""
      }
      onSelect={selectProblem}
    />
  );
}

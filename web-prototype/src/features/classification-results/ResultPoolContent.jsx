import { ResultPoolStatus } from "./ResultPoolStatus";
import { Pagination } from "./ClassificationResultCommon";
import { ResultPoolRow } from "./ClassificationResultListParts";
import { resultVersionId } from "./resultActionPolicy";

/** @typedef {import("./classificationResultListContracts").ResultPoolContext} ResultPoolContext */

/** @param {ResultPoolContext} context */
export function ResultPoolContent(context) {
  const {
    route,
    updateRoute,
    selectedIds,
    toggleSelection,
    runPrimaryAction,
    data,
    loading,
    error,
    totalPages,
    changePage,
    changePageSize,
  } = context;
  return (
    <section className="result-pool-card">
      <ResultPoolStatus {...context} />{" "}
      {data && data.items.length > 0 && !error && (
        <>
          <div
            className={`result-pool-table is-selecting ${loading ? "is-loading" : ""}`}
          >
            <div className="result-pool-head" role="row">
              <span>选择</span>
              <span>结果状态</span>
              <span>Listing / 店铺</span>
              <span>产品名称</span>
              <span>数据规模</span>
              <span>发布时间</span>
              <span>操作</span>
            </div>
            {data.items.map((result) => (
              <ResultPoolRow
                key={result.version_id}
                result={result}
                selectable
                selected={selectedIds.has(resultVersionId(result))}
                onToggle={() => toggleSelection(result)}
                onPrimary={() => runPrimaryAction(result)}
                onOpen={() =>
                  updateRoute({
                    version: result.version_id,
                    recordPage: 1,
                    problem: "",
                    productName: "",
                    productSku: "",
                    orderId: "",
                  })
                }
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

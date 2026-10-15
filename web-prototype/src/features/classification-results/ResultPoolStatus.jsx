import { Package } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { ResultError } from "./ClassificationResultCommon";
import { navigateHash } from "../../app/hashRouter";

/** @param {import("./classificationResultListContracts").ResultPoolContext} context */
export function ResultPoolStatus({
  loading,
  data,
  error,
  load,
  activeFilters,
  clearFilters,
}) {
  return (
    <>
      {" "}
      {loading && !data && <InlineLoading scope="page" label="正在读取分类结果…" />}
      {error && <ResultError message={error} onRetry={load} hasData={Boolean(data)} />}
      {!loading && !error && data?.items?.length === 0 && (
        <ResultPoolEmpty activeFilters={activeFilters} clearFilters={clearFilters} />
      )}
    </>
  );
}

/** @param {Pick<import("./classificationResultListContracts").ResultPoolContext, "activeFilters" | "clearFilters">} props */
function ResultPoolEmpty({ activeFilters, clearFilters }) {
  return (
    <EmptyState
      icon={Package}
      title={activeFilters ? "没有符合条件的结果" : "结果池还是空的"}
      description={
        activeFilters
          ? "调整筛选条件后重新查询。"
          : "Listing 分析完成后，可在这里查看分类结果和反馈证据。"
      }
      action={
        <button
          className="secondary-button"
          onClick={() => (activeFilters ? clearFilters() : navigateHash("task-create"))}
        >
          {activeFilters ? "清除筛选" : "创建分析任务"}
        </button>
      }
    />
  );
}

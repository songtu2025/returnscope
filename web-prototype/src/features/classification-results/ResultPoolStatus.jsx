import { Package } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { ResultError } from "./ClassificationResultCommon";

/** @param {import("./classificationResultListContracts").ResultPoolContext} context */
export function ResultPoolStatus({ loading, data, error, load, activeFilters }) {
  return (
    <>
      {" "}
      {loading && !data && <InlineLoading label="正在读取分类结果…" />}
      {error && <ResultError message={error} onRetry={load} />}
      {!loading && !error && data?.items?.length === 0 && (
        <ResultPoolEmpty activeFilters={activeFilters} />
      )}
    </>
  );
}

/** @param {{activeFilters: boolean}} props */
function ResultPoolEmpty({ activeFilters }) {
  return (
    <EmptyState
      icon={Package}
      title={activeFilters ? "没有符合条件的结果" : "结果池还是空的"}
      description={
        activeFilters
          ? "调整筛选条件后重新查询。"
          : "Listing 片段完成并发布后，会在这里形成不可变结果版本。"
      }
    />
  );
}

import { SummaryMetric } from "./ClassificationResultDetailParts";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailMetrics(context) {
  const {
    result,
    readyRecords,
    reviewRecords,
    excludedRecords,
    unusableRecords,
    modelErrorRecords,
  } = context;
  return (
    <section className="result-summary-grid" aria-label="分类结果摘要">
      <SummaryMetric label="订单/退货记录" value={result.record_count} />
      <SummaryMetric label="分类单元" value={result.unit_count} />
      <SummaryMetric label="可用记录" value={readyRecords ?? 0} tone="green" />
      <SummaryMetric label="需复核记录" value={reviewRecords ?? 0} tone="amber" />
      <SummaryMetric label="已忽略记录" value={excludedRecords ?? 0} />
      <SummaryMetric
        label="不可用记录"
        value={unusableRecords ?? 0}
        note={`其中模型异常 ${Number(modelErrorRecords || 0).toLocaleString()} 条`}
        tone="red"
      />
    </section>
  );
}

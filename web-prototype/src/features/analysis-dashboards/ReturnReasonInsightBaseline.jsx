import { formatPercent } from "./returnReasonInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */

/** @param {{data: DashboardInsights, route: DashboardRoute, loading: boolean, error?: string}} props */
export function ReturnReasonInsightBaseline({ data, route, loading, error }) {
  const selected = data.selected_reason;
  return (
    <section className="return-insight-baseline-info" aria-label="基线计算明细">
      <h3>基线计算明细</h3>
      {loading ? (
        <p role="status">正在更新计算明细…</p>
      ) : error ? (
        <p role="alert">当前筛选更新失败，请重试后查看计算明细。</p>
      ) : !selected ? (
        <p>当前范围没有可计算的原因。</p>
      ) : (
        <>
          <BaselineScope data={data} route={route} />
          <p>
            当前原因：{selected.label}
            。基线使用以上范围内的全部有效反馈，原因类别只影响原因选择。
            {data.counting_basis === "feedback_group"
              ? "按反馈组去重。"
              : "按原始记录统计。"}
          </p>
          <BaselineComparisonTable data={data} />
        </>
      )}
    </section>
  );
}

/** @param {{data: DashboardInsights, route: DashboardRoute}} props */
function BaselineScope({ data, route }) {
  return (
    <p>
      {route.dateFrom || data.date_range?.date_from || "不限开始日期"} 至{" "}
      {route.dateTo || data.date_range?.date_to || "不限结束日期"} ·{" "}
      {route.listing || "全部 Listing"} · {route.productName || "全部产品"} ·{" "}
      {route.productSku || "全部 SKU"} ·{" "}
      {data.subject_breakdown?.find((item) => item.value === route.subject)?.label ||
        "全部问题对象"}
    </p>
  );
}

/** @param {DashboardInsights} data */
function baselineRows(data) {
  const selected = data.selected_reason;
  return [
    ...(data.products ?? []).map((item) => ({
      key: `product-${item.value}`,
      label: `商品：${item.value}`,
      count: item.record_count,
      total: item.total_record_count,
      baselineCount: selected?.record_count,
      lift: item.lift,
    })),
    ...(data.co_reasons ?? []).map((item) => ({
      key: `reason-${item.value}`,
      label: `伴随原因：${item.label}`,
      count: item.record_count,
      total: selected?.record_count,
      baselineCount: item.baseline_record_count,
      lift: item.lift,
    })),
  ];
}

/** @param {{data: DashboardInsights}} props */
function BaselineComparisonTable({ data }) {
  const total = data.total_record_count;
  const rows = baselineRows(data);
  return (
    <div className="return-insight-baseline-table">
      <table>
        <caption>相对倍数 = 当前比例 ÷ 基线比例，使用未四舍五入的比例计算</caption>
        <thead>
          <tr>
            <th scope="col">比较项</th>
            <th scope="col">当前命中 / 样本量</th>
            <th scope="col">基线命中 / 样本量</th>
            <th scope="col">相对倍数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              <td>
                {row.count.toLocaleString()} / {row.total?.toLocaleString() ?? "--"}
                {row.total ? ` = ${formatPercent((row.count / row.total) * 100)}` : ""}
              </td>
              <td>
                {row.baselineCount?.toLocaleString() ?? "--"} /{" "}
                {total?.toLocaleString() ?? "--"}
                {total && row.baselineCount !== undefined
                  ? ` = ${formatPercent((row.baselineCount / total) * 100)}`
                  : ""}
              </td>
              <td>{row.lift === undefined ? "--" : `${row.lift.toFixed(2)}×`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

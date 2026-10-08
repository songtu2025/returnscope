import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { number, percent } from "./AiInsightReportPresentation";
/** @typedef {import("./analysisDashboardContracts").ReportHotspot} ReportHotspot */
/** @typedef {{code: string, label: string, rows: ReportHotspot[]}} HotspotGroup */

/** @param {{group: HotspotGroup, baseline: number, upperBound: number}} props */
function BenchmarkPlot({ group, baseline, upperBound }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={group.rows}
        layout="vertical"
        margin={{ top: 10, right: 62, bottom: 8, left: 12 }}
      >
        <CartesianGrid stroke="#e8edea" horizontal={false} />
        <XAxis
          type="number"
          domain={[0, upperBound]}
          tickFormatter={(value) => `${value}%`}
          tick={{ fill: "#66736d", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="category"
          dataKey="value"
          width={170}
          tick={{ fill: "#34463d", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(value, name, item) => [
            `${percent(value)} · ${number(item.payload.record_count)} / ${number(
              item.payload.total_record_count,
            )} 条 · ${number(item.payload.lift).toFixed(2)}×`,
            name,
          ]}
        />
        <ReferenceLine x={baseline} stroke="#8b9690" strokeDasharray="4 4" />
        <Bar
          name="商品内占比"
          dataKey="product_reason_rate"
          fill={group.code === "FIT_TOO_SMALL" ? "#23775e" : "#b77a27"}
          radius={[0, 3, 3, 0]}
          barSize={15}
        >
          <LabelList
            dataKey="product_reason_rate"
            position="right"
            formatter={percent}
            fill="#435249"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** @param {{group: HotspotGroup}} props */
function HotspotBenchmark({ group }) {
  const baseline = number(group.rows[0]?.overall_reason_rate);
  const maxRate = Math.max(
    baseline,
    ...group.rows.map((item) => number(item.product_reason_rate)),
  );
  const upperBound = Math.max(10, Math.ceil((maxRate + 5) / 5) * 5);

  return (
    <figure className="ai-report-benchmark-figure">
      <figcaption>
        <div>
          <span>{group.label}高风险商品</span>
          <b>商品内发生比例与整体基线比较</b>
        </div>
        <strong>整体 {percent(baseline)}</strong>
      </figcaption>
      <div className="ai-report-benchmark-chart">
        <BenchmarkPlot group={group} baseline={baseline} upperBound={upperBound} />
      </div>
      <p>虚线为整体基线；悬停可查看相关记录、商品样本量和相对倍数。</p>
    </figure>
  );
}

/** @param {{groups: HotspotGroup[]}} props */
export function ReportHotspotBenchmarks({ groups }) {
  if (!groups.length) return null;
  return (
    <div className="ai-report-benchmark-section">
      <div className="ai-report-subheading">
        <span>商品热点与整体基线</span>
        <p>优先关注“商品内占比明显高于整体、且超额记录较多”的商品。</p>
      </div>
      {groups.map((group) => (
        <HotspotBenchmark group={group} key={group.code} />
      ))}
    </div>
  );
}

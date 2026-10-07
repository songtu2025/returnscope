import { BusinessIssueGrid } from "./AiInsightReportBusinessIssues";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EvidenceLine, SectionHeading } from "./AiInsightReportCommon";
import {
  date,
  number,
  percent,
  shortDate,
  signedPercentagePoints,
} from "./AiInsightReportPresentation";
import { analysisContextTerms } from "./analysisContextPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").ReportBusinessIssue} ReportBusinessIssue */
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").ReportHotspot} ReportHotspot */
/** @typedef {import("./analysisDashboardContracts").ReportTrendSummary} ReportTrendSummary */
/** @typedef {import("./AiInsightReportPresentation").SizeTrendRow} SizeTrendRow */
/** @typedef {{code: string, label: string, rows: ReportHotspot[]}} HotspotGroup */

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
              tick={{ fill: "#7a867f", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              type="category"
              dataKey="value"
              width={170}
              tick={{ fill: "#34463d", fontSize: 10 }}
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
                fontSize={10}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p>虚线为整体基线；悬停可查看相关记录、商品样本量和相对倍数。</p>
    </figure>
  );
}

/** @param {{diagnosticFinding?: ReportFinding, hasBusinessIssues: boolean, businessIssues: ReportBusinessIssue[], smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary, sizeTrend: SizeTrendRow[], hotspotBenchmarks: HotspotGroup[], otherFindings: ReportFinding[], catalog: InsightEvidenceCatalog, analysisContext: string}} props */
export function ReportDiagnosticsSection({
  diagnosticFinding,
  hasBusinessIssues,
  businessIssues,
  smallTrend,
  largeTrend,
  sizeTrend,
  hotspotBenchmarks,
  otherFindings,
  catalog,
  analysisContext,
}) {
  const terms = analysisContextTerms(analysisContext);
  if (
    !diagnosticFinding &&
    !hasBusinessIssues &&
    sizeTrend.length === 0 &&
    otherFindings.length === 0
  ) {
    return null;
  }

  return (
    <section className="ai-report-section" id="report-diagnostic">
      <SectionHeading
        number="02"
        title={diagnosticFinding?.title || "关键发现与业务含义"}
        description="比较时间变化和商品内部发生比例，避免把总量误当成整改优先级。"
      />
      {diagnosticFinding && (
        <div className="ai-report-editorial-intro">
          <p>
            <b>{diagnosticFinding.conclusion}</b>
          </p>
          <p>{diagnosticFinding.interpretation}</p>
        </div>
      )}

      {hasBusinessIssues && (
        <BusinessIssueGrid issues={businessIssues} analysisContext={analysisContext} />
      )}

      {(smallTrend.status === "available" || largeTrend.status === "available") && (
        <div className="ai-report-delta-strip" aria-label="尺码问题趋势变化摘要">
          {smallTrend.status === "available" && (
            <div className="small">
              <span>偏小 · 最近 {number(smallTrend.window_weeks)} 周</span>
              <strong>
                {signedPercentagePoints(smallTrend.delta_percentage_points)}
              </strong>
              <p>
                {percent(smallTrend.early_rate)} → {percent(smallTrend.recent_rate)}
              </p>
            </div>
          )}
          {largeTrend.status === "available" && (
            <div className="large">
              <span>偏大 · 最近 {number(largeTrend.window_weeks)} 周</span>
              <strong>
                {signedPercentagePoints(largeTrend.delta_percentage_points)}
              </strong>
              <p>
                {percent(largeTrend.early_rate)} → {percent(largeTrend.recent_rate)}
              </p>
            </div>
          )}
        </div>
      )}

      {sizeTrend.length >= 8 && (
        <figure className="ai-report-trend-figure">
          <figcaption>
            <div>
              <b>偏小与偏大问题占比趋势</b>
              <span>按完整自然周统计，占当周{terms.includedLabel}的比例</span>
            </div>
            <div className="ai-report-chart-legend" aria-label="图例">
              <span>
                <i className="small" />
                偏小
                {smallTrend.status === "available" && (
                  <b>{percent(smallTrend.recent_rate)}</b>
                )}
              </span>
              <span>
                <i className="large" />
                偏大
                {largeTrend.status === "available" && (
                  <b>{percent(largeTrend.recent_rate)}</b>
                )}
              </span>
            </div>
          </figcaption>
          <div
            className="ai-report-trend-chart"
            role="img"
            aria-label="偏小与偏大问题占比的每周变化"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={sizeTrend}
                margin={{ top: 12, right: 18, bottom: 4, left: 0 }}
              >
                <CartesianGrid stroke="#e5ebe7" vertical={false} />
                <XAxis
                  dataKey="period_start"
                  tickFormatter={shortDate}
                  tick={{ fill: "#66736c", fontSize: 10 }}
                  tickLine={false}
                  axisLine={{ stroke: "#cfd9d3" }}
                  minTickGap={34}
                />
                <YAxis
                  domain={[0, "auto"]}
                  tickFormatter={(value) => `${value}%`}
                  tick={{ fill: "#66736c", fontSize: 10 }}
                  tickLine={false}
                  axisLine={false}
                  width={38}
                />
                <Tooltip
                  labelFormatter={(value) => `周起始 ${date(value)}`}
                  formatter={(value, name) => [`${number(value).toFixed(1)}%`, name]}
                />
                <Line
                  name="偏小"
                  type="monotone"
                  dataKey="too_small"
                  stroke="#176f56"
                  strokeWidth={2.4}
                  dot={false}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
                <Line
                  name="偏大"
                  type="monotone"
                  dataKey="too_large"
                  stroke="#b7791f"
                  strokeWidth={2.4}
                  dot={false}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p>
            趋势用于识别问题方向变化；它描述样本结构，不能单独证明尺码设计变化造成了结果。
          </p>
        </figure>
      )}

      {hotspotBenchmarks.length > 0 && (
        <div className="ai-report-benchmark-section">
          <div className="ai-report-subheading">
            <span>商品热点与整体基线</span>
            <p>优先关注“商品内占比明显高于整体、且超额记录较多”的商品。</p>
          </div>
          {hotspotBenchmarks.map((group) => (
            <HotspotBenchmark group={group} key={group.code} />
          ))}
        </div>
      )}

      {diagnosticFinding && (
        <div className="ai-report-implication">
          <span>这意味着</span>
          <p>{diagnosticFinding.implication}</p>
        </div>
      )}

      {diagnosticFinding && (
        <EvidenceLine ids={diagnosticFinding.evidence_ids} catalog={catalog} />
      )}
      {otherFindings.length > 0 && (
        <div className="ai-report-generated-findings">
          {otherFindings.map((finding) => (
            <article key={finding.id || finding.title}>
              <h4>{finding.title}</h4>
              <b>{finding.conclusion}</b>
              <p>{finding.interpretation}</p>
              <p>
                <b>业务含义：</b>
                {finding.implication}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

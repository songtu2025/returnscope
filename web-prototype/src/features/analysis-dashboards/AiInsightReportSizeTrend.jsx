import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  date,
  number,
  percent,
  shortDate,
  signedPercentagePoints,
} from "./AiInsightReportPresentation";
import { analysisContextTerms } from "./analysisContextPresentation";
/** @typedef {import("./analysisDashboardContracts").ReportTrendSummary} ReportTrendSummary */
/** @typedef {import("./AiInsightReportPresentation").SizeTrendRow} SizeTrendRow */
/** @typedef {ReturnType<typeof analysisContextTerms>} AnalysisContextTerms */

/** @param {{smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary}} props */
function TrendDeltaStrip({ smallTrend, largeTrend }) {
  return (
    <div className="ai-report-delta-strip" aria-label="尺码问题趋势变化摘要">
      {smallTrend.status === "available" && (
        <div className="small">
          <span>偏小 · 最近 {number(smallTrend.window_weeks)} 周</span>
          <strong>{signedPercentagePoints(smallTrend.delta_percentage_points)}</strong>
          <p>
            {percent(smallTrend.early_rate)} → {percent(smallTrend.recent_rate)}
          </p>
        </div>
      )}
      {largeTrend.status === "available" && (
        <div className="large">
          <span>偏大 · 最近 {number(largeTrend.window_weeks)} 周</span>
          <strong>{signedPercentagePoints(largeTrend.delta_percentage_points)}</strong>
          <p>
            {percent(largeTrend.early_rate)} → {percent(largeTrend.recent_rate)}
          </p>
        </div>
      )}
    </div>
  );
}

/** @param {{sizeTrend: SizeTrendRow[]}} props */
function SizeTrendPlot({ sizeTrend }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={sizeTrend} margin={{ top: 12, right: 18, bottom: 4, left: 0 }}>
        <CartesianGrid stroke="#e5ebe7" vertical={false} />
        <XAxis
          dataKey="period_start"
          tickFormatter={shortDate}
          tick={{ fill: "#66736c", fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: "#cfd9d3" }}
          minTickGap={34}
        />
        <YAxis
          domain={[0, "auto"]}
          tickFormatter={(value) => `${value}%`}
          tick={{ fill: "#66736c", fontSize: 12 }}
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
  );
}

/** @param {{smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary}} props */
function TrendLegend({ smallTrend, largeTrend }) {
  return (
    <div className="ai-report-chart-legend" aria-label="图例">
      <span>
        <i className="small" />
        偏小
        {smallTrend.status === "available" && <b>{percent(smallTrend.recent_rate)}</b>}
      </span>
      <span>
        <i className="large" />
        偏大
        {largeTrend.status === "available" && <b>{percent(largeTrend.recent_rate)}</b>}
      </span>
    </div>
  );
}

/** @param {{smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary, sizeTrend: SizeTrendRow[], terms: AnalysisContextTerms}} props */
function TrendFigure({ smallTrend, largeTrend, sizeTrend, terms }) {
  return (
    <figure className="ai-report-trend-figure">
      <figcaption>
        <div>
          <b>偏小与偏大问题占比趋势</b>
          <span>按完整自然周统计，占当周{terms.includedLabel}的比例</span>
        </div>
        <TrendLegend smallTrend={smallTrend} largeTrend={largeTrend} />
      </figcaption>
      <div
        className="ai-report-trend-chart"
        role="img"
        aria-label="偏小与偏大问题占比的每周变化"
      >
        <SizeTrendPlot sizeTrend={sizeTrend} />
      </div>
      <p>
        趋势用于识别问题方向变化；它描述样本结构，不能单独证明尺码设计变化造成了结果。
      </p>
    </figure>
  );
}

/** @param {{smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary, sizeTrend: SizeTrendRow[], analysisContext: string}} props */
export function ReportSizeTrend({
  smallTrend,
  largeTrend,
  sizeTrend,
  analysisContext,
}) {
  const terms = analysisContextTerms(analysisContext);
  return (
    <>
      {(smallTrend.status === "available" || largeTrend.status === "available") && (
        <TrendDeltaStrip smallTrend={smallTrend} largeTrend={largeTrend} />
      )}
      {sizeTrend.length >= 8 && (
        <TrendFigure
          smallTrend={smallTrend}
          largeTrend={largeTrend}
          sizeTrend={sizeTrend}
          terms={terms}
        />
      )}
    </>
  );
}

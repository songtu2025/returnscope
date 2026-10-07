import { number, percent, signedPercentagePoints } from "./AiInsightReportPresentation";
import { businessIssueView } from "./reportBusinessIssuePresentation";
import { BusinessIssueContext } from "./AiInsightReportBusinessContext";
/** @typedef {import("./analysisDashboardContracts").ReportBusinessIssue} ReportBusinessIssue */
/** @typedef {ReturnType<typeof import("./reportBusinessIssuePresentation").businessIssueView>} BusinessIssueView */

/** @param {{issue: ReportBusinessIssue}} props */
function BusinessIssueHeader({ issue }) {
  return (
    <header>
      <div>
        <span>{issue.role === "primary" ? "优先验证" : "辅助信号"}</span>
        <h4>{issue.label || issue.reason_code}</h4>
        <p>{issue.label_group || "评论问题"}</p>
      </div>
      <div className="ai-report-business-issue-share">
        <strong>{percent(issue.percentage)}</strong>
        <span>{number(issue.record_count).toLocaleString()} 条相关记录</span>
      </div>
    </header>
  );
}

/** @param {{issue: ReportBusinessIssue, view: BusinessIssueView}} props */
function BusinessIssueMetrics({ issue, view }) {
  const { leadHotspot, leadRate, baseline, trend } = view;
  return (
    <div className="ai-report-business-issue-metrics">
      <div>
        <span>最集中{issue.hotspot_label || "商品变体"}</span>
        <strong>{leadHotspot?.value || "尚未形成热点"}</strong>
        {leadHotspot && (
          <small>
            {percent(leadRate)} · 比整体{signedPercentagePoints(leadRate - baseline)}
          </small>
        )}
      </div>
      <div>
        <span>相对整体基线</span>
        <strong>{leadHotspot ? `${number(leadHotspot.lift).toFixed(2)}×` : "—"}</strong>
        <small>{leadHotspot ? `整体 ${percent(baseline)}` : "证据不足"}</small>
      </div>
      <div>
        <span>近期样本变化</span>
        <strong>
          {trend.status === "available"
            ? signedPercentagePoints(trend.delta_percentage_points)
            : "—"}
        </strong>
        <small>
          {trend.status === "available"
            ? `${percent(trend.early_rate)} → ${percent(trend.recent_rate)}`
            : "完整周期不足"}
        </small>
      </div>
    </div>
  );
}

/** @param {{issue: ReportBusinessIssue, hotspots: BusinessIssueView["hotspots"]}} props */
function BusinessIssueHotspots({ issue, hotspots }) {
  return (
    <div className="ai-report-business-hotspots">
      <div className="ai-report-business-hotspot-heading">
        <span>{issue.hotspot_label || "商品变体"}</span>
        <span>问题占比</span>
        <span>整体基线</span>
        <span>相对倍数</span>
      </div>
      {hotspots.map((hotspot, index) => (
        <div key={`${hotspot.value}-${index}`}>
          <b>{hotspot.value || `变体 ${index + 1}`}</b>
          <span>{percent(hotspot.product_reason_rate)}</span>
          <span>{percent(hotspot.overall_reason_rate)}</span>
          <strong>{number(hotspot.lift).toFixed(2)}×</strong>
        </div>
      ))}
    </div>
  );
}

/** @param {{issue: ReportBusinessIssue, analysisContext: string}} props */
function BusinessIssueCard({ issue, analysisContext }) {
  const view = businessIssueView(issue, analysisContext);
  return (
    <article className="ai-report-business-issue">
      <BusinessIssueHeader issue={issue} />
      <BusinessIssueMetrics issue={issue} view={view} />
      {view.hotspots.length > 0 && (
        <BusinessIssueHotspots issue={issue} hotspots={view.hotspots} />
      )}
      <BusinessIssueContext view={view} />
      <footer>
        <b>下一步验证</b>
        <p>{issue.validation_focus}</p>
      </footer>
    </article>
  );
}

/** @param {{issues: ReportBusinessIssue[], analysisContext: string}} props */
export function BusinessIssueGrid({ issues, analysisContext }) {
  if (!issues.length) return null;
  return (
    <div className="ai-report-business-issues">
      {issues.map((issue) => (
        <BusinessIssueCard
          issue={issue}
          analysisContext={analysisContext}
          key={issue.id || issue.reason_code}
        />
      ))}
    </div>
  );
}

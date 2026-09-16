import {
  CheckCircle,
  Database,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";

import { InsightReportVersionSelect } from "./AiInsightDecisionReport";
import { EvidenceLine, SectionHeading } from "./AiInsightReportCommon";
import {
  date,
  number,
  percent,
  QUALITY_GATE_LABELS,
  reportLabel,
  STATUS_LABELS,
} from "./AiInsightReportPresentation";
import { dashboardVersionNumber } from "./dashboardFields";

/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").InsightReportSource} InsightReportSource */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {import("./analysisDashboardContracts").InsightSummary} InsightSummary */
/** @typedef {import("./analysisDashboardContracts").LegacyInsightReportContent} LegacyInsightReportContent */
/** @typedef {import("./analysisDashboardContracts").ReportDataQuality} ReportDataQuality */
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").ReportReadiness} ReportReadiness */

/** @param {{report: InsightReport, reports: InsightReport[], dashboard: Dashboard, version: DashboardVersion | null, content: LegacyInsightReportContent, source: InsightReportSource, qualityStatus?: string, decisionReadiness?: ReportReadiness, onSelect: (reportId: string) => void}} props */
export function ReportCover({
  report,
  reports,
  dashboard,
  version,
  content,
  source,
  qualityStatus,
  decisionReadiness,
  onSelect,
}) {
  return (
    <header className="ai-report-cover" aria-labelledby="ai-report-name">
      <div>
        <span>AI 洞察报告 · 报告 V{report.version_no}</span>
        <h2 id="ai-report-name">{content.title || `${dashboard.name}洞察报告`}</h2>
        <p>
          分析周期 {date(source.date_range?.date_from)}–
          {date(source.date_range?.date_to)}
          <i />
          数据版本 v
          {report.dashboard_version_no || dashboardVersionNumber(version) || 1}
        </p>
      </div>
      <div className="ai-report-cover-status">
        <span>
          {report.resolved_model || report.model_name || report.model_key} ·{" "}
          {report.reasoning_effort}
        </span>
        {source.report_status === "provisional" && (
          <strong className="ai-report-provisional">临时报告</strong>
        )}
        <strong className="ai-report-generation-status">
          <CheckCircle size={17} /> {STATUS_LABELS[report.status]}
        </strong>
        {qualityStatus && (
          <strong className={`ai-report-quality-status ${qualityStatus}`}>
            {QUALITY_GATE_LABELS[qualityStatus] || qualityStatus}
          </strong>
        )}
        {decisionReadiness?.status && (
          <strong
            className={`ai-report-decision-status ${decisionReadiness.status}`}
            title={decisionReadiness.reason}
          >
            {decisionReadiness.label || decisionReadiness.status}
          </strong>
        )}
        <InsightReportVersionSelect
          report={report}
          reports={reports}
          onSelect={onSelect}
          optionLabel={(item) => `${reportLabel(item)} · ${STATUS_LABELS[item.status]}`}
        />
      </div>
    </header>
  );
}

/** @param {{scrollTo: (id: string) => void}} props */
export function ReportChapterNavigation({ scrollTo }) {
  return (
    <nav className="ai-report-chapters" aria-label="报告目录">
      <button onClick={() => scrollTo("report-summary")}>执行摘要</button>
      <button onClick={() => scrollTo("report-structure")}>问题结构</button>
      <button onClick={() => scrollTo("report-diagnostic")}>问题诊断</button>
      <button onClick={() => scrollTo("report-actions")}>行动计划</button>
    </nav>
  );
}

/** @param {{content: LegacyInsightReportContent, summary: InsightSummary, source: InsightReportSource, productMapping: ReportDataQuality, textQuality: ReportDataQuality}} props */
export function ReportExecutiveSummary({
  content,
  summary,
  source,
  productMapping,
  textQuality,
}) {
  return (
    <section className="ai-report-executive" id="report-summary">
      <span className="ai-report-eyebrow">Executive Summary</span>
      <h3>执行摘要</h3>
      <ol className="ai-report-summary-list ai-report-generated-summary">
        {(content.executive_summary ?? []).map((item, index) => (
          <li className={item.tone || "neutral"} key={item.title}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <b>{item.title}</b>
              <p>{item.statement}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="ai-report-trust-strip" aria-label="报告可信范围">
        <div>
          <Database size={18} />
          <span>已纳入</span>
          <b>{number(summary.record_count).toLocaleString()} 条</b>
        </div>
        <div>
          <ShieldCheck size={18} />
          <span>标签覆盖</span>
          <b>{percent(source.label_coverage)}</b>
        </div>
        <div className={number(summary.pending_review_record_count) ? "warning" : ""}>
          <WarningCircle size={18} />
          <span>待审核</span>
          <b>{number(summary.pending_review_record_count).toLocaleString()} 条</b>
        </div>
        <p>多标签问题占比不可直接相加；当前占比描述退货样本结构，不代表真实退货率。</p>
      </div>
      {productMapping.status === "needs_review" && (
        <div className="ai-report-review-note">
          <b>商品主数据需先核对：</b> {productMapping.note}
        </div>
      )}
      {textQuality.status === "needs_review" && (
        <div className="ai-report-review-note">
          <b>评论文本质量未通过：</b> {textQuality.note}
          异常文本已从评论证据中排除；其余聚合结果仍可用于问题验证，
          不可直接下发商品整改。
        </div>
      )}
    </section>
  );
}

/** @param {{structureFinding?: ReportFinding, groups: InsightReason[], primaryGroup?: InsightReason, maxGroupCount: number, catalog: InsightEvidenceCatalog}} props */
export function ReportStructureSection({
  structureFinding,
  groups,
  primaryGroup,
  maxGroupCount,
  catalog,
}) {
  return (
    <section className="ai-report-section" id="report-structure">
      <SectionHeading
        number="01"
        title={structureFinding?.title || "退货问题结构"}
        description="先区分可行动的商品问题与宽泛的非商品原因。"
      />
      <div className="ai-report-editorial-intro">
        <p>
          <b>{structureFinding?.conclusion}</b>
        </p>
        <p>{structureFinding?.interpretation}</p>
      </div>
      {groups.length > 0 && (
        <figure className="ai-report-structure-figure">
          <figcaption>
            <div>
              <span>首要可行动问题</span>
              <strong>{primaryGroup?.value || "当前问题组"}</strong>
            </div>
            <b>{percent(primaryGroup?.percentage)}</b>
            <small>
              {number(primaryGroup?.record_count).toLocaleString()} 条相关记录
            </small>
          </figcaption>
          <div className="ai-report-size-bars" aria-label="退货问题组规模比较">
            {groups.slice(0, 6).map((group) => (
              <div key={group.value}>
                <span>{group.value}</span>
                <i aria-hidden="true">
                  <span
                    style={{
                      width: `${Math.max(
                        (number(group.record_count) / maxGroupCount) * 100,
                        2,
                      )}%`,
                    }}
                  />
                </i>
                <b>{percent(group.percentage)}</b>
                <em>{number(group.record_count).toLocaleString()} 条</em>
              </div>
            ))}
          </div>
        </figure>
      )}
      <div className="ai-report-implication">
        <span>这意味着</span>
        <p>{structureFinding?.implication}</p>
      </div>
      <EvidenceLine ids={structureFinding?.evidence_ids} catalog={catalog} />
    </section>
  );
}

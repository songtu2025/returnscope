import { GitBranch } from "@phosphor-icons/react";

import { InlineLoading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import {
  dashboardVersionNumber,
  productCatalogVersionLabel,
  resultSourceVersionNumber,
} from "./dashboardFields";
import { AiInsightReport } from "./AiInsightReport";
import { ReturnReasonInsights } from "./ReturnReasonInsights";
import { asItems, dashboardVersionId } from "./DashboardDetailHelpers";

/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardContentState} DashboardContentState */
/** @typedef {import("./analysisDashboardContracts").DashboardDecisionState} DashboardDecisionState */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardReportState} DashboardReportState */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardSource} DashboardSource */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */
/** @typedef {DashboardSource[] | {sources?: DashboardSource[], items?: DashboardSource[]}} DashboardSourceData */
/**
 * @typedef {Object} DashboardDetailContentProps
 * @property {DashboardRoute} route
 * @property {UpdateDashboardRoute} updateRoute
 * @property {DashboardContentState} content
 * @property {DashboardReportState} reports
 * @property {InsightReport | null} selectedReport
 * @property {InsightReport[]} publishedReports
 * @property {InsightReport[]} generationAttempts
 * @property {InsightReport | null} latestPublishedReport
 * @property {Dashboard} dashboard
 * @property {DashboardVersion | null} selectedVersion
 * @property {DashboardVersion[]} versions
 * @property {string} currentVersionId
 * @property {DashboardDecisionState} decisionState
 * @property {() => void | Promise<void>} onReloadContent
 * @property {(record: DashboardRecord, trigger: HTMLElement | null) => void} onEvidence
 * @property {() => void | Promise<void>} onReloadReports
 * @property {() => void | Promise<void>} onOpenReportGeneration
 * @property {() => void | Promise<void>} onRetryReport
 * @property {(issueId: string, status: string) => void | Promise<void>} onIssueDecision
 * @property {(issueId: string) => void} onSelectIssue
 * @property {(reportId: string) => void} onSelectReport
 * @property {(versionId: string) => void} onSelectVersion
 */

/** @param {DashboardDetailContentProps} props */
export function DashboardDetailContent({
  route,
  updateRoute,
  content,
  reports,
  selectedReport,
  publishedReports,
  generationAttempts,
  latestPublishedReport,
  dashboard,
  selectedVersion,
  versions,
  currentVersionId,
  decisionState,
  onReloadContent,
  onEvidence,
  onReloadReports,
  onOpenReportGeneration,
  onRetryReport,
  onIssueDecision,
  onSelectIssue,
  onSelectReport,
  onSelectVersion,
}) {
  return (
    <>
      {content.loading && !content.data && <InlineLoading label="正在读取看板数据…" />}
      {content.error && (
        <section className="dashboard-error" role="alert">
          <b>看板数据读取失败</b>
          <span>{content.error}</span>
          <button className="secondary-button" onClick={onReloadContent}>
            重新加载
          </button>
        </section>
      )}
      {!content.error && route.tab === "overview" && content.data && (
        <ReturnReasonInsights
          route={route}
          updateRoute={updateRoute}
          data={
            /** @type {import("./analysisDashboardContracts").DashboardInsights} */ (
              content.data
            )
          }
          loading={content.loading}
          onEvidence={onEvidence}
        />
      )}
      {route.tab === "report" && reports.loading && !reports.items.length && (
        <InlineLoading label="正在读取 AI 洞察报告…" />
      )}
      {route.tab === "report" && reports.error && (
        <section className="dashboard-error" role="alert">
          <b>AI 洞察报告读取失败</b>
          <span>{reports.error}</span>
          <button className="secondary-button" onClick={onReloadReports}>
            重新加载
          </button>
        </section>
      )}
      {route.tab === "report" && !reports.error && !reports.loading && (
        <AiInsightReport
          report={selectedReport}
          reports={publishedReports}
          attempts={generationAttempts}
          latestReport={latestPublishedReport}
          dashboard={dashboard}
          version={selectedVersion}
          onGenerate={onOpenReportGeneration}
          onRetry={onRetryReport}
          selectedIssueId={route.issueId}
          decisionState={decisionState}
          onDecision={onIssueDecision}
          onSelectIssue={onSelectIssue}
          onSelect={onSelectReport}
        />
      )}
      {!content.error && route.tab === "source" && content.data && (
        <DashboardDetailSources
          data={/** @type {DashboardSourceData} */ (content.data)}
          version={selectedVersion}
        />
      )}
      {route.tab === "history" && (
        <DashboardDetailHistory
          versions={versions}
          currentVersionId={currentVersionId}
          onSelect={onSelectVersion}
        />
      )}
    </>
  );
}

/** @param {{data: DashboardSourceData, version: DashboardVersion | null}} props */
function DashboardDetailSources({ data, version }) {
  const sources = asItems(Array.isArray(data) ? data : (data.sources ?? data));
  return (
    <section className="dashboard-lineage-card">
      <header>
        <GitBranch size={22} />
        <div>
          <b>数据来源与血缘</b>
          <span>
            看板 v{dashboardVersionNumber(version) ?? "-"} → 看板数据集 v
            {dashboardVersionNumber(version) ?? "-"} → Listing 分类结果版本
          </span>
          <small className="dashboard-dataset-technical-id">
            数据集ID：<code>{version?.dataset_version_id || "未提供"}</code>
          </small>
        </div>
      </header>
      <div className="dashboard-source-mapping">
        <div className="dashboard-source-head">
          <span>店铺/站点</span>
          <span>Listing</span>
          <span>分类结果版本</span>
          <span>产品信息版本</span>
          <span>记录数</span>
          <span>质量</span>
        </div>
        {sources.map((source, index) => (
          <div key={source.result_version_id || source.version_id || index}>
            <span>{source.store_site || "未提供"}</span>
            <b>{source.listing || "未提供"}</b>
            <span>v{resultSourceVersionNumber(source) || "-"}</span>
            <span title={productCatalogVersionLabel(source)}>
              {productCatalogVersionLabel(source)}
            </span>
            <span>{Number(source.record_count || 0).toLocaleString()}</span>
            <span>
              {source.quality_status === "ready"
                ? "可用"
                : source.quality_status || "未提供"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

/** @param {{versions: DashboardVersion[], currentVersionId: string, onSelect: (versionId: string) => void}} props */
function DashboardDetailHistory({ versions, currentVersionId, onSelect }) {
  return (
    <section className="dashboard-history-card">
      <header>
        <b>看板版本历史</b>
        <span>旧版本始终只读，不会随分类结果变化。</span>
      </header>
      <ol>
        {versions.map((version) => {
          const id = dashboardVersionId(version);
          return (
            <li key={id} className={id === currentVersionId ? "current" : ""}>
              <span>v{dashboardVersionNumber(version)}</span>
              <div>
                <b>看板数据集 v{dashboardVersionNumber(version)}</b>
                <p>
                  {version.source_change_summary || version.reason || "未提供版本原因"}
                </p>
                <small className="dashboard-dataset-technical-id">
                  数据集ID：<code>{version.dataset_version_id || "未提供"}</code>
                </small>
                <small>
                  {version.created_by_name || "未提供创建人"} ·{" "}
                  {formatTime(version.created_at)}
                </small>
              </div>
              <button
                className="secondary-button compact-button"
                onClick={() => onSelect(id)}
              >
                查看版本
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

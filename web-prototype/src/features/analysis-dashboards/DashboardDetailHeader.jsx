import {
  ArrowLeft,
  ArrowsClockwise,
  DownloadSimple,
  Info,
  Sparkle,
} from "@phosphor-icons/react";
import Button from "antd/es/button";

import { dashboardVersionNumber } from "./dashboardFields";
import { dashboardVersionId } from "./DashboardDetailHelpers";
import { analysisContextTerms } from "./analysisContextPresentation";
import { DeliveryLifecycleControls } from "../../components/DeliveryLifecycleControls";

/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardTab} DashboardTab */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/**
 * @typedef {Object} DashboardDetailHeaderProps
 * @property {Dashboard} dashboard
 * @property {DashboardVersion | null} selectedVersion
 * @property {boolean} showReport
 * @property {InsightReport | null} selectedReport
 * @property {string} analysisContext
 * @property {boolean} showDataInfo
 * @property {DashboardVersion[]} versions
 * @property {string} versionId
 * @property {DashboardTab} activeTab
 * @property {string} currentVersionId
 * @property {boolean} isCurrentVersion
 * @property {() => void} onBack
 * @property {() => void | Promise<void>} onOpenReportGeneration
 * @property {() => void} onExport
 * @property {() => void} onOpenReport
 * @property {() => void} onToggleDataInfo
 * @property {(versionId: string) => void} onSelectVersion
 * @property {() => void} onShowSources
 * @property {() => void} onShowHistory
 * @property {() => void} onShowOverview
 * @property {() => void} onShowReport
 * @property {() => void | Promise<void>} [onChanged]
 * @property {() => void} [onEdit]
 */

/** @param {DashboardDetailHeaderProps} props */
export function DashboardDetailHeader({
  dashboard,
  selectedVersion,
  showReport,
  selectedReport,
  analysisContext,
  showDataInfo,
  versions,
  versionId,
  activeTab,
  currentVersionId,
  isCurrentVersion,
  onBack,
  onOpenReportGeneration,
  onExport,
  onOpenReport,
  onToggleDataInfo,
  onSelectVersion,
  onShowSources,
  onShowHistory,
  onShowOverview,
  onShowReport,
  onChanged,
  onEdit,
}) {
  const terms = analysisContextTerms(analysisContext);
  const reportLinkLabel = isCurrentVersion ? "AI 洞察报告" : "查看最新 AI 报告";
  return (
    <>
      <header className="return-insight-page-header">
        <div>
          <Button
            size="small"
            className="page-loading-navigation"
            aria-label="返回分析看板列表"
            icon={<ArrowLeft size={18} />}
            onClick={onBack}
          />
          <h1>{showReport ? terms.reportTitle : terms.pageTitle}</h1>
          <span>{dashboard.name || "未命名看板"}</span>
        </div>
        <div className="return-insight-header-actions">
          {!dashboard.deleted_at && onEdit && (
            <Button onClick={onEdit}>编辑看板</Button>
          )}
          <DeliveryLifecycleControls
            kind="dashboard"
            id={dashboard.id}
            name={dashboard.name || "分析看板"}
            revision={dashboard.revision}
            deleted={Boolean(dashboard.deleted_at)}
            onChanged={onChanged}
          />
          {showReport ? (
            <>
              <button
                className="secondary-button"
                disabled={Boolean(dashboard.deleted_at)}
                onClick={onOpenReportGeneration}
              >
                <ArrowsClockwise size={17} /> {selectedReport ? "重新生成" : "生成报告"}
              </button>
              <button
                className="secondary-button"
                disabled={selectedReport?.status !== "completed"}
                onClick={onExport}
              >
                <DownloadSimple size={17} /> 导出
              </button>
            </>
          ) : (
            <Button
              type="primary"
              className="ai-report-open-button"
              icon={<Sparkle size={17} />}
              onClick={onOpenReport}
            >
              {reportLinkLabel}
            </Button>
          )}
          <Button
            className={`return-insight-info-button ${showDataInfo ? "active" : ""}`}
            aria-expanded={showDataInfo}
            icon={<Info size={17} />}
            onClick={onToggleDataInfo}
          >
            数据说明
          </Button>
        </div>
      </header>

      {showDataInfo && (
        <section className="return-insight-data-info">
          <div>
            <b>{dashboard.description || "当前看板基于已发布分类结果生成"}</b>
            <span>看板自动显示当前分类结果；历史数据可在修改历史中查看。</span>
          </div>
          {activeTab === "history" && (
            <label>
              历史数据
              <select
                aria-label="历史数据"
                value={versionId}
                onChange={(event) => onSelectVersion(event.target.value)}
              >
                {versions.map((version) => (
                  <option
                    key={dashboardVersionId(version)}
                    value={dashboardVersionId(version)}
                  >
                    v{dashboardVersionNumber(version)}
                    {dashboardVersionId(version) === currentVersionId ? "（当前）" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Button type="link" onClick={onShowSources}>
            数据来源
          </Button>
          <Button type="link" onClick={onShowHistory}>
            修改历史
          </Button>
        </section>
      )}

      {!isCurrentVersion && (
        <div className="dashboard-readonly-notice" role="status">
          当前查看历史版本 v{dashboardVersionNumber(selectedVersion)}，数据与配置只读。
        </div>
      )}

      {activeTab !== "overview" && (
        <nav
          className="result-detail-tabs return-insight-secondary-tabs"
          aria-label="分析看板详情"
        >
          <button onClick={onShowOverview}>
            {isCurrentVersion ? "洞察看板" : "返回最新洞察看板"}
          </button>
          <button
            className={activeTab === "report" ? "active" : ""}
            onClick={onShowReport}
          >
            {reportLinkLabel}
          </button>
          <button
            className={activeTab === "source" ? "active" : ""}
            onClick={onShowSources}
          >
            数据来源
          </button>
          <button
            className={activeTab === "history" ? "active" : ""}
            onClick={onShowHistory}
          >
            修改历史
          </button>
        </nav>
      )}
    </>
  );
}

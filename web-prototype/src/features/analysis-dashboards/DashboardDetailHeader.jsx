import {
  ArrowLeft,
  ArrowsClockwise,
  DownloadSimple,
  Info,
  Sparkle,
} from "@phosphor-icons/react";

import { dashboardVersionNumber } from "./dashboardFields";
import { dashboardVersionId } from "./DashboardDetailHelpers";

export function DashboardDetailHeader({
  dashboard,
  selectedVersion,
  showReport,
  selectedReport,
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
  onCreateVersion,
  onShowOverview,
  onShowReport,
}) {
  return (
    <>
      <header className="return-insight-page-header">
        <div>
          <button
            className="return-insight-back"
            aria-label="返回分析看板列表"
            onClick={onBack}
          >
            <ArrowLeft size={18} />
          </button>
          <h1>{showReport ? "AI退货洞察报告" : "退货原因洞察"}</h1>
          <span>{dashboard.name || "未命名看板"}</span>
        </div>
        <div className="return-insight-header-actions">
          {showReport ? (
            <>
              <button className="secondary-button" onClick={onOpenReportGeneration}>
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
            <button
              className="primary-button ai-report-open-button"
              onClick={onOpenReport}
            >
              <Sparkle size={17} /> AI 洞察报告
            </button>
          )}
          <button
            className={`secondary-button return-insight-info-button ${
              showDataInfo ? "active" : ""
            }`}
            aria-expanded={showDataInfo}
            onClick={onToggleDataInfo}
          >
            <Info size={17} /> 数据说明
          </button>
        </div>
      </header>

      {showDataInfo && (
        <section className="return-insight-data-info">
          <div>
            <b>{dashboard.description || "当前看板基于已发布分类结果生成"}</b>
            <span>
              看板版本 v{dashboardVersionNumber(selectedVersion)} · 历史版本只读且可追溯
            </span>
          </div>
          <label>
            看板版本
            <select
              aria-label="看板版本"
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
          <button className="text-button" onClick={onShowSources}>
            数据来源
          </button>
          <button className="text-button" onClick={onShowHistory}>
            版本历史
          </button>
          <button
            className="primary-button"
            disabled={!isCurrentVersion}
            title={isCurrentVersion ? "" : "历史版本只读，请切换到当前版本"}
            onClick={onCreateVersion}
          >
            创建新版本
          </button>
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
          <button onClick={onShowOverview}>洞察看板</button>
          <button
            className={activeTab === "report" ? "active" : ""}
            onClick={onShowReport}
          >
            AI 洞察报告
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
            版本历史
          </button>
        </nav>
      )}
    </>
  );
}

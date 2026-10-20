import { DashboardReportGeneration } from "./DashboardReportGeneration";
import { useState } from "react";
import "../../styles/insight-generation.css";
import "../../styles/classification-results.css";
import "../../styles/return-insights.css";
import "../../styles/ai-insight-reports.css";
import { DashboardDetailContent } from "./DashboardDetailContent";
import { DashboardDetailHeader } from "./DashboardDetailHeader";
import { DashboardSettingsEditor } from "./DashboardSettingsEditor";
import { ReportLifecyclePanel } from "./ReportLifecyclePanel";
import { dashboardVersionId } from "./DashboardDetailHelpers";
import {
  DashboardDetailError,
  DashboardDetailLoading,
} from "./DashboardDetailStateViews";
import { dashboardAnalysisContext } from "./analysisContextPresentation";
import { useDashboardVersion } from "./useDashboardVersion";
import { useDashboardContent } from "./useDashboardContent";
import { useDashboardReports } from "./useDashboardReports";
import { useDashboardReportActions } from "./useDashboardReportActions";

/** @typedef {import("./dashboardDetailContracts").Dashboard} Dashboard */
/** @typedef {import("./dashboardDetailContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps} props */
export function DashboardDetail(props) {
  const [editingSettings, setEditingSettings] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const { route, updateRoute } = props;
  const { content, loadContent } = useDashboardContent(props);
  const reportState = useDashboardReports(props);
  const {
    reports,
    loadReports,
    publishedReports,
    generationAttempts,
    latestPublishedReport,
    selectedReport,
  } = reportState;
  const {
    decisionState,
    generationOpen,
    setGenerationOpen,
    generationState,
    generationForm,
    setGenerationForm,
    openReportGeneration,
    reloadGenerationModels,
    submitReportGeneration,
    retryReport,
    cancelReport,
    cancelling,
    setIssueDecision,
  } = useDashboardReportActions({ ...props, ...reportState });

  const { main, selectedVersion, loadMain } = useDashboardVersion({
    ...props,
    protectedOperation:
      evidenceOpen || generationOpen || decisionState.loading || editingSettings,
  });

  const [showDataInfo, setShowDataInfo] = useState(false);

  if (main.error && !main.dashboard) {
    return (
      <DashboardDetailError
        error={main.error}
        onBack={() => updateRoute({ dashboardId: "", versionId: "" })}
        onReload={() => loadMain()}
      />
    );
  }
  if (!main.dashboard) {
    return <DashboardDetailLoading />;
  }

  const dashboard = main.dashboard;
  const currentVersionId = currentDashboardVersion(dashboard, main.versions);
  const isCurrentVersion = !currentVersionId || currentVersionId === route.versionId;
  const showReport = route.tab === "report";
  const analysisContext = dashboardAnalysisContext(content.data, selectedReport);
  /** @param {"overview" | "report"} tab */
  const showLatestView = (tab) =>
    updateRoute({
      tab,
      versionId: currentVersionId || route.versionId,
      ...(!isCurrentVersion
        ? {
            reportId: "",
            issueId: "",
            problem: "",
            labelGroup: "",
            recordPage: 1,
            reasonPage: 0,
          }
        : {}),
    });

  return (
    <div className="standard-page analysis-dashboard-page dashboard-detail-page return-insight-page">
      {main.error && (
        <DashboardDetailError
          error={main.error}
          onReload={() => loadMain(true)}
          hasData
        />
      )}
      <DashboardDetailHeader
        onEdit={() => setEditingSettings(true)}
        dashboard={dashboard}
        onChanged={loadMain}
        selectedVersion={selectedVersion}
        showReport={showReport}
        selectedReport={selectedReport}
        analysisContext={analysisContext}
        showDataInfo={showDataInfo}
        versions={main.versions}
        versionId={route.versionId}
        activeTab={route.tab}
        currentVersionId={currentVersionId}
        isCurrentVersion={isCurrentVersion}
        onBack={() => updateRoute({ dashboardId: "", versionId: "", tab: "overview" })}
        onOpenReportGeneration={openReportGeneration}
        onExport={() => window.print()}
        onOpenReport={() => showLatestView("report")}
        onToggleDataInfo={() => setShowDataInfo((visible) => !visible)}
        onSelectVersion={
          /** @param {string} versionId */ (versionId) =>
            updateRoute({
              versionId,
              reportId: "",
              issueId: "",
              tab: "history",
              recordPage: 1,
              reasonPage: 0,
              problem: "",
              labelGroup: "",
              subject: "",
              listing: "",
              productName: "",
              productSku: "",
              orderId: "",
              dateFrom: "",
              dateTo: "",
            })
        }
        onShowSources={() => updateRoute({ tab: "source" })}
        onShowHistory={() => updateRoute({ tab: "history" })}
        onShowOverview={() => showLatestView("overview")}
        onShowReport={() => showLatestView("report")}
      />

      {editingSettings && (
        <DashboardSettingsEditor
          dashboard={dashboard}
          onClose={() => setEditingSettings(false)}
          onSaved={async (id) => {
            setEditingSettings(false);
            updateRoute({ versionId: id, tab: "overview" });
            await loadMain();
          }}
        />
      )}
      {showReport && (
        <ReportLifecyclePanel
          dashboardId={dashboard.id}
          versionId={route.versionId}
          report={selectedReport}
          onChanged={() => loadReports()}
        />
      )}
      <DashboardDetailContent
        route={route}
        showDataInfo={showDataInfo}
        updateRoute={updateRoute}
        content={content}
        reports={reports}
        selectedReport={selectedReport}
        publishedReports={publishedReports}
        generationAttempts={generationAttempts}
        latestPublishedReport={latestPublishedReport}
        dashboard={dashboard}
        selectedVersion={selectedVersion}
        versions={main.versions}
        currentVersionId={currentVersionId}
        decisionState={decisionState}
        analysisContext={analysisContext}
        onReloadContent={loadContent}
        onEvidenceOpenChange={setEvidenceOpen}
        onReloadReports={loadReports}
        onOpenReportGeneration={openReportGeneration}
        onRetryReport={retryReport}
        onCancelReport={cancelReport}
        cancelling={cancelling}
        onIssueDecision={setIssueDecision}
        onSelectIssue={
          /** @param {string} issueId */ (issueId) =>
            updateRoute({ issueId }, { replace: true })
        }
        onSelectReport={
          /** @param {string} reportId */ (reportId) =>
            updateRoute({ reportId, issueId: "" }, { replace: true })
        }
        onSelectVersion={
          /** @param {string} versionId */ (versionId) =>
            updateRoute({ versionId, tab: "history" })
        }
      />

      {generationOpen && (
        <DashboardReportGeneration
          dashboard={dashboard}
          selectedVersion={selectedVersion}
          generationForm={generationForm}
          setGenerationForm={setGenerationForm}
          setGenerationOpen={setGenerationOpen}
          submitReportGeneration={submitReportGeneration}
          generationState={generationState}
          reloadGenerationModels={reloadGenerationModels}
          analysisContext={analysisContext}
        />
      )}
    </div>
  );
}

/** @param {Dashboard} dashboard @param {DashboardVersion[]} versions */
function currentDashboardVersion(dashboard, versions) {
  return (
    dashboard.current_version_id ||
    dashboardVersionId(versions.find((version) => version.is_current) || {})
  );
}

import { DashboardReportGeneration } from "./DashboardReportGeneration";
import { useRef, useState } from "react";
import "../../styles/insight-generation.css";
import "../../styles/classification-results.css";
import "../../styles/return-insights.css";
import "../../styles/ai-insight-reports.css";
import { navigateHash } from "../../app/hashRouter";
import { createDashboardSelection } from "./dashboardSelectionStorage";
import { DashboardDetailContent } from "./DashboardDetailContent";
import { DashboardDetailEvidenceDrawer } from "./DashboardDetailEvidenceDrawer";
import { DashboardDetailHeader } from "./DashboardDetailHeader";
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
/** @typedef {import("./dashboardDetailContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps} props */
export function DashboardDetail(props) {
  const { route, updateRoute, userId } = props;
  const { main, selectedVersion, loadMain } = useDashboardVersion(props);
  const { content, selectedRecord, setSelectedRecord, loadContent } =
    useDashboardContent(props);
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
    submitReportGeneration,
    retryReport,
    setIssueDecision,
  } = useDashboardReportActions({ ...props, ...reportState });

  const [showDataInfo, setShowDataInfo] = useState(false);
  /** @type {import("react").RefObject<HTMLElement | null>} */
  const evidenceTriggerRef = useRef(null);

  if (main.error) {
    return (
      <DashboardDetailError
        error={main.error}
        onBack={() => updateRoute({ dashboardId: "", versionId: "" })}
        onReload={loadMain}
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
  const createVersion = () => {
    const token = createDashboardSelection(userId, {
      target_dashboard_id: route.dashboardId,
      expected_revision: dashboard.revision,
    });
    navigateHash("classification-results", { selection_token: token });
  };
  const analysisContext = dashboardAnalysisContext(content.data, selectedReport);

  return (
    <div className="standard-page analysis-dashboard-page dashboard-detail-page return-insight-page">
      <DashboardDetailHeader
        dashboard={dashboard}
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
        onOpenReport={() =>
          updateRoute({
            tab: "report",
            problem: "",
            labelGroup: "",
            recordPage: 1,
          })
        }
        onToggleDataInfo={() => setShowDataInfo((visible) => !visible)}
        onSelectVersion={
          /** @param {string} versionId */ (versionId) =>
            updateRoute({
              versionId,
              reportId: "",
              issueId: "",
              tab: "overview",
              recordPage: 1,
              reasonPage: 0,
              hierarchyPage: 1,
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
        onCreateVersion={createVersion}
        onShowOverview={() => updateRoute({ tab: "overview" })}
        onShowReport={() => updateRoute({ tab: "report", problem: "", labelGroup: "" })}
      />

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
        onEvidence={(
          /** @type {DashboardRecord} */ record,
          /** @type {HTMLElement | null} */ trigger,
        ) => {
          evidenceTriggerRef.current = trigger;
          setSelectedRecord(record);
        }}
        onReloadReports={loadReports}
        onOpenReportGeneration={openReportGeneration}
        onRetryReport={retryReport}
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

      {selectedRecord && (
        <DashboardDetailEvidenceDrawer
          record={selectedRecord}
          onClose={() => setSelectedRecord(null)}
          returnFocusRef={evidenceTriggerRef}
          analysisContext={analysisContext}
        />
      )}
      {generationOpen && (
        <DashboardReportGeneration
          dashboard={dashboard}
          selectedVersion={selectedVersion}
          selectedReport={selectedReport}
          generationForm={generationForm}
          setGenerationForm={setGenerationForm}
          setGenerationOpen={setGenerationOpen}
          submitReportGeneration={submitReportGeneration}
          generationState={generationState}
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

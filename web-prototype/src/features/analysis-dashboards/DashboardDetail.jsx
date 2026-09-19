import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "../../styles/insight-generation.css";
import "../../styles/classification-results.css";
import "../../styles/return-insights.css";
import "../../styles/ai-insight-reports.css";

import { navigateHash } from "../../app/hashRouter";
import { api } from "../../api";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { dashboardVersionNumber } from "./dashboardFields";
import { createDashboardSelection } from "./dashboardSelectionStorage";
import { DashboardDetailContent } from "./DashboardDetailContent";
import { DashboardDetailEvidenceDrawer } from "./DashboardDetailEvidenceDrawer";
import { DashboardDetailHeader } from "./DashboardDetailHeader";
import {
  asItems,
  dashboardVersionId,
  isPublishedReport,
} from "./DashboardDetailHelpers";
import {
  DashboardDetailError,
  DashboardDetailLoading,
} from "./DashboardDetailStateViews";
import { InsightGenerationModal } from "./InsightGenerationModal";
import { dashboardAnalysisContext } from "./analysisContextPresentation";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "./insightModelOptions";

/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").ReportDecision} ReportDecision */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").InsightModel} InsightModel */
/** @typedef {import("./analysisDashboardContracts").DashboardContentData} DashboardContentData */
/** @typedef {import("./analysisDashboardContracts").DashboardContentState} DashboardContentState */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardDetailRoute */

/**
 * @typedef {Object} DashboardDetailProps
 * @property {DashboardDetailRoute} route
 * @property {import("./analysisDashboardContracts").UpdateDashboardRoute} updateRoute
 * @property {import("./analysisDashboardContracts").DashboardNotify} notify
 * @property {string} userId
 */

/** @param {unknown} error */
function errorName(error) {
  return error instanceof Error ? error.name : "";
}

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

/** @param {InsightReport} report */
function decisionIssues(report) {
  const content = report.content;
  return content && "issues" in content && Array.isArray(content.issues)
    ? content.issues
    : [];
}

/** @param {DashboardDetailProps} props */
export function DashboardDetail({ route, updateRoute, notify, userId }) {
  const [main, setMain] = useState(
    /** @returns {{loading: boolean, error: string, dashboard: Dashboard | null, versions: DashboardVersion[]}} */ () => ({
      loading: true,
      error: "",
      dashboard: null,
      versions: [],
    }),
  );
  const [content, setContent] = useState(
    /** @returns {DashboardContentState} */ () => ({
      loading: true,
      error: "",
      data: null,
    }),
  );
  const [reports, setReports] = useState(
    /** @returns {{loading: boolean, error: string, items: InsightReport[]}} */ () => ({
      loading: false,
      error: "",
      items: [],
    }),
  );
  const [decisionState, setDecisionState] = useState({
    issueId: "",
    loading: false,
    error: "",
  });
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationState, setGenerationState] = useState(
    /** @returns {{loading: boolean, submitting: boolean, error: string, models: InsightModel[]}} */ () => ({
      loading: false,
      submitting: false,
      error: "",
      models: [],
    }),
  );
  const [generationForm, setGenerationForm] = useState({
    modelId: "",
    effort: "high",
  });
  const [selectedRecord, setSelectedRecord] = useState(
    /** @returns {DashboardRecord | null} */ () => null,
  );
  const [showDataInfo, setShowDataInfo] = useState(false);
  /** @type {import("react").RefObject<HTMLElement | null>} */
  const evidenceTriggerRef = useRef(null);
  const mainGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const mainControllerRef = useRef(null);
  const contentGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const contentControllerRef = useRef(null);
  const reportGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const reportControllerRef = useRef(null);

  const loadMain = useCallback(async () => {
    const generation = mainGenerationRef.current + 1;
    mainGenerationRef.current = generation;
    mainControllerRef.current?.abort();
    const controller = new AbortController();
    mainControllerRef.current = controller;
    setMain((current) => ({ ...current, loading: true, error: "" }));
    try {
      /** @type {[Dashboard, DashboardVersion[] | {items?: DashboardVersion[]}]} */
      const [dashboard, versionsResponse] = await Promise.all([
        dashboardApi.analysisDashboard(route.dashboardId, route.versionId, {
          signal: controller.signal,
        }),
        dashboardApi.analysisDashboardVersions(route.dashboardId, {
          signal: controller.signal,
        }),
      ]);
      if (mainGenerationRef.current !== generation) return;
      /** @type {DashboardVersion[]} */
      const versions = asItems(versionsResponse);
      setMain({ loading: false, error: "", dashboard, versions });
      const selectedVersionId =
        route.versionId ||
        dashboard.current_version_id ||
        dashboardVersionId(versions[0] || {});
      if (selectedVersionId && selectedVersionId !== route.versionId) {
        updateRoute({ versionId: selectedVersionId }, { replace: true });
      }
    } catch (error) {
      if (
        mainGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setMain((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [route.dashboardId, route.versionId, updateRoute]);

  useEffect(() => {
    loadMain();
    return () => {
      mainGenerationRef.current += 1;
      mainControllerRef.current?.abort();
    };
  }, [loadMain]);

  const selectedVersion = useMemo(
    () =>
      main.versions.find(
        (version) => dashboardVersionId(version) === route.versionId,
      ) ||
      main.dashboard?.version ||
      null,
    [main.dashboard, main.versions, route.versionId],
  );
  const filters = useMemo(
    () => ({
      problem: route.problem,
      label_group: route.labelGroup,
      listing: route.listing,
      product_name: route.productName,
      product_sku: route.productSku,
      date_from: route.dateFrom,
      date_to: route.dateTo,
    }),
    [
      route.dateFrom,
      route.dateTo,
      route.labelGroup,
      route.listing,
      route.problem,
      route.productName,
      route.productSku,
    ],
  );
  const loadContent = useCallback(async () => {
    if (!route.versionId || route.tab === "history" || route.tab === "report") {
      setContent({ loading: false, error: "", data: null });
      return;
    }
    const generation = contentGenerationRef.current + 1;
    contentGenerationRef.current = generation;
    contentControllerRef.current?.abort();
    const controller = new AbortController();
    contentControllerRef.current = controller;
    setContent((current) => ({ ...current, loading: true, error: "" }));
    try {
      /** @type {DashboardContentData} */
      let data;
      if (route.tab === "source") {
        data = /** @type {DashboardContentData} */ (
          await dashboardApi.analysisDashboardSources(
            route.dashboardId,
            route.versionId,
            { signal: controller.signal },
          )
        );
      } else {
        data = /** @type {DashboardContentData} */ (
          await dashboardApi.analysisDashboardInsights(
            route.dashboardId,
            route.versionId,
            filters,
            { signal: controller.signal },
          )
        );
      }
      if (contentGenerationRef.current === generation) {
        setContent({ loading: false, error: "", data });
      }
    } catch (error) {
      if (
        contentGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setContent((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [filters, route.dashboardId, route.tab, route.versionId]);

  useEffect(() => {
    setSelectedRecord(null);
    loadContent();
    return () => {
      contentGenerationRef.current += 1;
      contentControllerRef.current?.abort();
    };
  }, [loadContent]);

  const loadReports = useCallback(async () => {
    if (route.tab !== "report" || !route.versionId) {
      setReports({ loading: false, error: "", items: [] });
      return;
    }
    const generation = reportGenerationRef.current + 1;
    reportGenerationRef.current = generation;
    reportControllerRef.current?.abort();
    const controller = new AbortController();
    reportControllerRef.current = controller;
    setReports((current) => ({ ...current, loading: true, error: "" }));
    try {
      const items = await dashboardApi.analysisDashboardInsightReports(
        route.dashboardId,
        route.versionId,
        { signal: controller.signal },
      );
      if (reportGenerationRef.current !== generation) return;
      /** @type {InsightReport[]} */
      const reportItems = asItems(items);
      setReports({ loading: false, error: "", items: reportItems });
    } catch (error) {
      if (
        reportGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setReports((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [route.dashboardId, route.tab, route.versionId]);

  useEffect(() => {
    loadReports();
    return () => {
      reportGenerationRef.current += 1;
      reportControllerRef.current?.abort();
    };
  }, [loadReports]);

  const publishedReports = reports.items.filter(isPublishedReport);
  const generationAttempts = reports.items.filter(
    (report) => !isPublishedReport(report),
  );
  const latestPublishedReport = publishedReports[0] || null;
  const selectedReport =
    reports.items.find((report) => report.id === route.reportId) ||
    latestPublishedReport ||
    generationAttempts[0] ||
    null;

  useEffect(() => {
    if (route.tab !== "report" || reports.loading || reports.error || !selectedReport) {
      return;
    }
    const issues =
      selectedReport.prompt_version === "ai-return-insight-v6" &&
      selectedReport.status === "completed"
        ? decisionIssues(selectedReport)
        : [];
    const issueId =
      issues.find((issue) => issue.id === route.issueId)?.id || issues[0]?.id || "";
    if (selectedReport.id === route.reportId && issueId === route.issueId) return;
    // 一次补全报告与问题，避免两个更新互相覆盖并反复加载正文。
    updateRoute({ reportId: selectedReport.id, issueId }, { replace: true });
  }, [
    reports.error,
    reports.loading,
    route.issueId,
    route.reportId,
    route.tab,
    selectedReport,
    updateRoute,
  ]);
  const activeReportId = generationAttempts.find((report) =>
    ["queued", "running"].includes(report.status),
  )?.id;

  useEffect(() => {
    if (!activeReportId) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const updated = await dashboardApi.insightReport(activeReportId);
        setReports((current) => ({
          ...current,
          items: current.items.map((item) => (item.id === updated.id ? updated : item)),
        }));
        if (updated.status === "completed") {
          notify?.("AI 洞察报告已生成");
        } else if (updated.status === "failed") {
          notify?.("AI 洞察报告生成未完成，可在报告页重试");
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeReportId, notify]);

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
  const currentVersionId =
    dashboard.current_version_id ||
    dashboardVersionId(main.versions.find((version) => version.is_current) || {});
  const isCurrentVersion = !currentVersionId || currentVersionId === route.versionId;
  const showReport = route.tab === "report";
  const createVersion = () => {
    const token = createDashboardSelection(userId, {
      target_dashboard_id: route.dashboardId,
      expected_revision: dashboard.revision,
    });
    navigateHash("classification-results", { selection_token: token });
  };
  const openReportGeneration = async () => {
    setGenerationOpen(true);
    setGenerationState({ loading: true, submitting: false, error: "", models: [] });
    const [configResult, preferenceResult] = await Promise.allSettled([
      typeof api.configs === "function" ? api.configs() : Promise.resolve([]),
      typeof api.modelPreference === "function"
        ? api.modelPreference()
        : Promise.resolve(null),
    ]);
    const configs = configResult.status === "fulfilled" ? configResult.value : [];
    const preference =
      preferenceResult.status === "fulfilled" ? preferenceResult.value : null;
    /** @type {InsightModel[]} */
    const models = insightModels(configs);
    const modelId = preferredInsightModel(configs, models, preference);
    const model = models.find((item) => item.id === modelId);
    setGenerationForm({ modelId, effort: preferredInsightEffort(model) });
    setGenerationState({
      loading: false,
      submitting: false,
      error:
        configResult.status === "rejected"
          ? errorMessage(configResult.reason) || "无法读取可用模型"
          : "",
      models,
    });
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submitReportGeneration = async (event) => {
    event.preventDefault();
    setGenerationState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.createAnalysisDashboardInsightReport(
        route.dashboardId,
        route.versionId,
        {
          model_id: generationForm.modelId,
          reasoning_effort: generationForm.effort,
        },
      );
      setReports((current) => ({
        loading: false,
        error: "",
        items: [report, ...current.items],
      }));
      setGenerationOpen(false);
      updateRoute({ reportId: report.id, issueId: "" }, { replace: true });
      notify?.("AI 洞察报告已加入生成队列");
    } catch (error) {
      setGenerationState((current) => ({
        ...current,
        submitting: false,
        error: errorMessage(error),
      }));
    }
  };
  const retryReport = async () => {
    if (!selectedReport) return;
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.retryInsightReport(selectedReport.id);
      setReports((current) => ({
        ...current,
        items: [report, ...current.items],
      }));
      updateRoute({ reportId: report.id, issueId: "" }, { replace: true });
      notify?.("新的生成尝试已加入队列，原失败记录已保留");
    } catch (error) {
      setReports((current) => ({ ...current, error: errorMessage(error) }));
    }
  };
  /**
   * @param {string} issueId
   * @param {string} status
   */
  const setIssueDecision = async (issueId, status) => {
    if (!selectedReport) return;
    setDecisionState({ issueId, loading: true, error: "" });
    try {
      /** @type {ReportDecision} */
      const decision = await dashboardApi.setInsightReportIssueDecision(
        selectedReport.id,
        issueId,
        status,
      );
      setReports((current) => ({
        ...current,
        items: current.items.map((item) => {
          if (item.id !== selectedReport.id) return item;
          const decisions = (item.decisions ?? []).filter(
            (value) => value.issue_id !== issueId,
          );
          return { ...item, decisions: [decision, ...decisions] };
        }),
      }));
      setDecisionState({ issueId: "", loading: false, error: "" });
      notify?.("问题状态已更新");
    } catch (error) {
      setDecisionState({ issueId, loading: false, error: errorMessage(error) });
    }
  };
  const reportSummary =
    selectedReport?.evidence?.analysis?.summary || selectedVersion?.summary || {};
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
              problem: "",
              labelGroup: "",
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
        <InsightGenerationModal
          form={generationForm}
          onChange={setGenerationForm}
          onClose={() => setGenerationOpen(false)}
          onSubmit={submitReportGeneration}
          models={generationState.models}
          loading={generationState.loading}
          submitting={generationState.submitting}
          error={generationState.error}
          ready
          scopeLabel={`${dashboard.name || "未命名看板"} · 数据版本 v${dashboardVersionNumber(selectedVersion) || 1}`}
          includedRecords={Number(reportSummary.record_count || 0)}
          unitCount={Number(reportSummary.unit_count || 0)}
          pendingRecords={Number(reportSummary.pending_review_record_count || 0)}
          excludedRecords={Number(reportSummary.excluded_record_count || 0)}
          analysisContext={analysisContext}
        />
      )}
    </div>
  );
}

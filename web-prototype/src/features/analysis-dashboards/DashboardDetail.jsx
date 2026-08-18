import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowsClockwise,
  DownloadSimple,
  GitBranch,
  Info,
  Sparkle,
  X,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  dashboardVersionNumber,
  productCatalogVersionLabel,
  resultSourceVersionNumber,
} from "./dashboardFields";
import { createDashboardSelection } from "./dashboardSelectionStorage";
import { AiInsightReport } from "./AiInsightReport";
import { InsightGenerationModal } from "./InsightGenerationModal";
import { ReturnReasonInsights } from "./ReturnReasonInsights";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "./insightModelOptions";

function dashboardVersionId(version) {
  return version.version_id || version.id;
}

function asItems(value) {
  return Array.isArray(value) ? value : (value?.items ?? []);
}

function isPublishedReport(report) {
  return report.status === "completed" && Boolean(report.version_no);
}

export function DashboardDetail({ route, updateRoute, notify, userId }) {
  const [main, setMain] = useState({
    loading: true,
    error: "",
    dashboard: null,
    versions: [],
  });
  const [content, setContent] = useState({ loading: true, error: "", data: null });
  const [reports, setReports] = useState({ loading: false, error: "", items: [] });
  const [generationOpen, setGenerationOpen] = useState(false);
  const [generationState, setGenerationState] = useState({
    loading: false,
    submitting: false,
    error: "",
    models: [],
  });
  const [generationForm, setGenerationForm] = useState({
    modelId: "",
    effort: "high",
  });
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [showDataInfo, setShowDataInfo] = useState(false);
  const evidenceTriggerRef = useRef(null);
  const mainGenerationRef = useRef(0);
  const mainControllerRef = useRef(null);
  const contentGenerationRef = useRef(0);
  const contentControllerRef = useRef(null);
  const reportGenerationRef = useRef(0);
  const reportControllerRef = useRef(null);

  const loadMain = useCallback(async () => {
    const generation = mainGenerationRef.current + 1;
    mainGenerationRef.current = generation;
    mainControllerRef.current?.abort();
    const controller = new AbortController();
    mainControllerRef.current = controller;
    setMain((current) => ({ ...current, loading: true, error: "" }));
    try {
      const [dashboard, versionsResponse] = await Promise.all([
        dashboardApi.analysisDashboard(route.dashboardId, route.versionId, {
          signal: controller.signal,
        }),
        dashboardApi.analysisDashboardVersions(route.dashboardId, {
          signal: controller.signal,
        }),
      ]);
      if (mainGenerationRef.current !== generation) return;
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
      if (mainGenerationRef.current === generation && error.name !== "AbortError") {
        setMain((current) => ({ ...current, loading: false, error: error.message }));
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
      let data;
      if (route.tab === "source") {
        data = await dashboardApi.analysisDashboardSources(
          route.dashboardId,
          route.versionId,
          { signal: controller.signal },
        );
      } else {
        data = await dashboardApi.analysisDashboardInsights(
          route.dashboardId,
          route.versionId,
          filters,
          { signal: controller.signal },
        );
      }
      if (contentGenerationRef.current === generation) {
        setContent({ loading: false, error: "", data });
      }
    } catch (error) {
      if (contentGenerationRef.current === generation && error.name !== "AbortError") {
        setContent((current) => ({ ...current, loading: false, error: error.message }));
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
      const reportItems = asItems(items);
      setReports({ loading: false, error: "", items: reportItems });
      const selected = reportItems.find((item) => item.id === route.reportId);
      const latestPublished = reportItems.find(isPublishedReport);
      const nextReportId =
        selected?.id || latestPublished?.id || reportItems[0]?.id || "";
      if (nextReportId !== route.reportId) {
        updateRoute({ reportId: nextReportId }, { replace: true });
      }
    } catch (error) {
      if (reportGenerationRef.current === generation && error.name !== "AbortError") {
        setReports((current) => ({ ...current, loading: false, error: error.message }));
      }
    }
  }, [route.dashboardId, route.reportId, route.tab, route.versionId, updateRoute]);

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

  if (main.loading && !main.dashboard) {
    return (
      <div className="standard-page analysis-dashboard-page">
        <InlineLoading label="正在读取分析看板…" />
      </div>
    );
  }
  if (main.error) {
    return (
      <div className="standard-page analysis-dashboard-page">
        <button
          className="text-button result-back-button"
          onClick={() => updateRoute({ dashboardId: "", versionId: "" })}
        >
          <ArrowLeft size={17} /> 返回分析看板
        </button>
        <section className="dashboard-error" role="alert">
          <b>分析看板详情读取失败</b>
          <span>{main.error}</span>
          <button className="secondary-button" onClick={loadMain}>
            重新加载
          </button>
        </section>
      </div>
    );
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
    const models = insightModels(configs);
    const modelId = preferredInsightModel(configs, models, preference);
    const model = models.find((item) => item.id === modelId);
    setGenerationForm({ modelId, effort: preferredInsightEffort(model) });
    setGenerationState({
      loading: false,
      submitting: false,
      error:
        configResult.status === "rejected"
          ? configResult.reason?.message || "无法读取可用模型"
          : "",
      models,
    });
  };
  const submitReportGeneration = async (event) => {
    event.preventDefault();
    setGenerationState((current) => ({ ...current, submitting: true, error: "" }));
    try {
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
      updateRoute({ reportId: report.id }, { replace: true });
      notify?.("AI 洞察报告已加入生成队列");
    } catch (error) {
      setGenerationState((current) => ({
        ...current,
        submitting: false,
        error: error.message,
      }));
    }
  };
  const retryReport = async () => {
    if (!selectedReport) return;
    try {
      const report = await dashboardApi.retryInsightReport(selectedReport.id);
      setReports((current) => ({
        ...current,
        items: [report, ...current.items],
      }));
      updateRoute({ reportId: report.id }, { replace: true });
      notify?.("新的生成尝试已加入队列，原失败记录已保留");
    } catch (error) {
      setReports((current) => ({ ...current, error: error.message }));
    }
  };
  const reportSummary =
    selectedReport?.evidence?.analysis?.summary || selectedVersion?.summary || {};

  return (
    <div className="standard-page analysis-dashboard-page dashboard-detail-page return-insight-page">
      <header className="return-insight-page-header">
        <div>
          <button
            className="return-insight-back"
            aria-label="返回分析看板列表"
            onClick={() =>
              updateRoute({ dashboardId: "", versionId: "", tab: "overview" })
            }
          >
            <ArrowLeft size={18} />
          </button>
          <h1>{showReport ? "AI退货洞察报告" : "退货原因洞察"}</h1>
          <span>{dashboard.name || "未命名看板"}</span>
        </div>
        <div className="return-insight-header-actions">
          {showReport ? (
            <>
              <button className="secondary-button" onClick={openReportGeneration}>
                <ArrowsClockwise size={17} /> {selectedReport ? "重新生成" : "生成报告"}
              </button>
              <button
                className="secondary-button"
                disabled={selectedReport?.status !== "completed"}
                onClick={() => window.print()}
              >
                <DownloadSimple size={17} /> 导出
              </button>
            </>
          ) : (
            <button
              className="primary-button ai-report-open-button"
              onClick={() =>
                updateRoute({
                  tab: "report",
                  problem: "",
                  labelGroup: "",
                  recordPage: 1,
                })
              }
            >
              <Sparkle size={17} /> AI 洞察报告
            </button>
          )}
          <button
            className={`secondary-button return-insight-info-button ${
              showDataInfo ? "active" : ""
            }`}
            aria-expanded={showDataInfo}
            onClick={() => setShowDataInfo((visible) => !visible)}
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
              value={route.versionId}
              onChange={(event) =>
                updateRoute({
                  versionId: event.target.value,
                  reportId: "",
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
            >
              {main.versions.map((version) => (
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
          <button
            className="text-button"
            onClick={() => updateRoute({ tab: "source" })}
          >
            数据来源
          </button>
          <button
            className="text-button"
            onClick={() => updateRoute({ tab: "history" })}
          >
            版本历史
          </button>
          <button
            className="primary-button"
            disabled={!isCurrentVersion}
            title={isCurrentVersion ? "" : "历史版本只读，请切换到当前版本"}
            onClick={createVersion}
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

      {route.tab !== "overview" && (
        <nav
          className="result-detail-tabs return-insight-secondary-tabs"
          aria-label="分析看板详情"
        >
          <button onClick={() => updateRoute({ tab: "overview" })}>洞察看板</button>
          <button
            className={route.tab === "report" ? "active" : ""}
            onClick={() => updateRoute({ tab: "report", problem: "", labelGroup: "" })}
          >
            AI 洞察报告
          </button>
          <button
            className={route.tab === "source" ? "active" : ""}
            onClick={() => updateRoute({ tab: "source" })}
          >
            数据来源
          </button>
          <button
            className={route.tab === "history" ? "active" : ""}
            onClick={() => updateRoute({ tab: "history" })}
          >
            版本历史
          </button>
        </nav>
      )}

      {content.loading && !content.data && <InlineLoading label="正在读取看板数据…" />}
      {content.error && (
        <section className="dashboard-error" role="alert">
          <b>看板数据读取失败</b>
          <span>{content.error}</span>
          <button className="secondary-button" onClick={loadContent}>
            重新加载
          </button>
        </section>
      )}
      {!content.error && route.tab === "overview" && content.data && (
        <ReturnReasonInsights
          route={route}
          updateRoute={updateRoute}
          data={content.data}
          loading={content.loading}
          onEvidence={(record, trigger) => {
            evidenceTriggerRef.current = trigger;
            setSelectedRecord(record);
          }}
        />
      )}
      {route.tab === "report" && reports.loading && !reports.items.length && (
        <InlineLoading label="正在读取 AI 洞察报告…" />
      )}
      {route.tab === "report" && reports.error && (
        <section className="dashboard-error" role="alert">
          <b>AI 洞察报告读取失败</b>
          <span>{reports.error}</span>
          <button className="secondary-button" onClick={loadReports}>
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
          onGenerate={openReportGeneration}
          onRetry={retryReport}
          onSelect={(reportId) => updateRoute({ reportId }, { replace: true })}
        />
      )}
      {!content.error && route.tab === "source" && content.data && (
        <DashboardSources data={content.data} version={selectedVersion} />
      )}
      {route.tab === "history" && (
        <DashboardHistory
          versions={main.versions}
          currentVersionId={currentVersionId}
          onSelect={(versionId) => updateRoute({ versionId, tab: "history" })}
        />
      )}

      {selectedRecord && (
        <DashboardEvidenceDrawer
          record={selectedRecord}
          onClose={() => setSelectedRecord(null)}
          returnFocusRef={evidenceTriggerRef}
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
          scopeLabel={`${dashboard.name || "未命名看板"} · 数据版本 v${
            dashboardVersionNumber(selectedVersion) || 1
          }`}
          includedRecords={Number(reportSummary.record_count || 0)}
          unitCount={Number(reportSummary.unit_count || 0)}
          pendingRecords={Number(reportSummary.pending_review_record_count || 0)}
          excludedRecords={Number(reportSummary.excluded_record_count || 0)}
        />
      )}
    </div>
  );
}

function DashboardSources({ data, version }) {
  const sources = asItems(data.sources ?? data);
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

function DashboardHistory({ versions, currentVersionId, onSelect }) {
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

function DashboardEvidenceDrawer({ record, onClose, returnFocusRef }) {
  const classification = record.classification ?? {};
  const semanticUnits = classification.semantic_units ?? [];
  const units = semanticUnits.length
    ? semanticUnits
    : (record.evidence ?? []).map((evidence) =>
        typeof evidence === "string" ? { evidence } : evidence,
      );
  const drawerRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return undefined;
    const returnFocus = returnFocusRef.current;
    const handleKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawer.querySelectorAll(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    closeButtonRef.current?.focus();
    drawer.addEventListener("keydown", handleKey);
    return () => {
      drawer.removeEventListener("keydown", handleKey);
      returnFocus?.focus();
    };
  }, [onClose, returnFocusRef]);

  return (
    <div className="evidence-drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        ref={drawerRef}
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dashboard-evidence-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span id="dashboard-evidence-title">分类结果与证据</span>
            <h2>{record.order_id || record.source_record_id || "未提供 order-id"}</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            aria-label="关闭证据抽屉"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>
        <section className="drawer-section">
          <b>业务信息</b>
          <DrawerField label="店铺/站点" value={record.store_site} />
          <DrawerField label="Listing" value={record.listing} />
          <DrawerField label="产品名称" value={record.product_name} />
          <DrawerField label="产品SKU" value={record.product_sku} />
          <DrawerField label="退货SKU（MSKU）" value={record.source_sku} />
          <DrawerField label="匹配MSKU" value={record.matched_msku} />
        </section>
        <section className="drawer-section">
          <b>退货原文</b>
          <DrawerField label="Amazon原因" value={record.amazon_reason} />
          <blockquote>{record.comment || "未提供退货评论"}</blockquote>
        </section>
        <section className="drawer-section">
          <b>分类结论</b>
          <DrawerField
            label="主要问题"
            value={classification.primary_label_codes?.join("、")}
          />
          <DrawerField
            label="问题标签"
            value={classification.problem_label_codes?.join("、")}
          />
        </section>
        <section className="drawer-section">
          <b>原文证据</b>
          {units.length === 0 && <p className="drawer-empty">没有提取到有效证据。</p>}
          {units.map((unit, index) => (
            <div className="evidence-unit" key={`${unit.label_code}-${index}`}>
              <span>{unit.label_code || "未标注"}</span>
              <blockquote>“{unit.evidence || "未提供证据"}”</blockquote>
              <small>
                部位：{unit.part || "未提供"} · 观点：{unit.opinion || "未提供"}
              </small>
            </div>
          ))}
        </section>
        <section className="drawer-section drawer-lineage">
          <b>运行来源</b>
          <DrawerField label="模型" value={classification.model_name} />
          <DrawerField label="提示词版本" value={classification.prompt_version} />
          <DrawerField label="分类体系" value={classification.taxonomy_version} />
          <DrawerField label="classification_key" value={record.classification_key} />
        </section>
      </aside>
    </div>
  );
}

function DrawerField({ label, value }) {
  return (
    <div className="drawer-field">
      <span>{label}</span>
      <b>{value || "未提供"}</b>
    </div>
  );
}

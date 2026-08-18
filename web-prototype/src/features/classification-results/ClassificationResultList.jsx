import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CaretRight,
  ChartBar,
  DownloadSimple,
  FunnelSimple,
  MagnifyingGlass,
  Package,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { InsightGenerationModal } from "../analysis-dashboards/InsightGenerationModal";
import {
  createDashboardSelection,
  readDashboardSelection,
  selectionItem,
  updateDashboardSelection,
} from "../analysis-dashboards/dashboardSelectionStorage";
import {
  insightModels,
  preferredInsightEffort,
  preferredInsightModel,
} from "../analysis-dashboards/insightModelOptions";
import { formatTime } from "../../lib/presentation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { Pagination, ResultError } from "./ClassificationResultCommon";
import { PUBLISH_LABELS } from "./classificationResultConstants";
import {
  isDashboardSelectable,
  resultActionPolicy,
  resultVersionId,
} from "./resultActionPolicy";
import { ResultWorkspaceNav } from "./ResultWorkspaceNav";

function productNames(result) {
  const names = Array.isArray(result.product_names)
    ? result.product_names.filter(Boolean)
    : result.product_name
      ? [result.product_name]
      : [];
  return names;
}

function selectedResultTotals(selected) {
  return selected.reduce(
    (total, item) => ({
      records: total.records + Number(item.record_count || 0),
      units: total.units + Number(item.unit_count || 0),
    }),
    { records: 0, units: 0 },
  );
}

export function ClassificationResultList({ route, updateRoute, notify, userId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasNewResults, setHasNewResults] = useState(false);
  const [filters, setFilters] = useState({
    q: route.q,
    storeSite: route.storeSite,
    listing: route.listing,
    qualityStatus: route.qualityStatus,
  });
  const firstResultRef = useRef("");
  const listGenerationRef = useRef(0);
  const listControllerRef = useRef(null);
  const pollGenerationRef = useRef(0);
  const pollControllerRef = useRef(null);
  const [selection, setSelection] = useState(() =>
    readDashboardSelection(userId, route.selectionToken),
  );
  const [insightOpen, setInsightOpen] = useState(false);
  const [insightState, setInsightState] = useState({
    loading: false,
    submitting: false,
    error: "",
    plan: null,
    models: [],
  });
  const [insightForm, setInsightForm] = useState({
    modelId: "",
    effort: "high",
  });

  useEffect(() => {
    setSelection(readDashboardSelection(userId, route.selectionToken));
  }, [route.selectionToken, userId]);

  const startSelection = () => {
    const token = createDashboardSelection(userId, { intent: "dashboard" });
    updateRoute({ selectionToken: token, page: 1 });
  };

  const selectedResults = useMemo(() => selection?.selected ?? [], [selection]);
  const selectionIntent = selection?.intent ?? "dashboard";
  const selectedIds = useMemo(
    () => new Set(selectedResults.map((item) => item.result_version_id)),
    [selectedResults],
  );
  const selectedTotals = useMemo(
    () => selectedResultTotals(selectedResults),
    [selectedResults],
  );

  const toggleSelection = (result) => {
    if (!isDashboardSelectable(result)) return;
    if (!route.selectionToken) {
      const token = createDashboardSelection(userId, {
        intent: "insight",
        selected: [selectionItem(result)],
      });
      setSelection(readDashboardSelection(userId, token));
      updateRoute({ selectionToken: token, page: 1 });
      return;
    }
    const id = resultVersionId(result);
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => {
      const selected = current.selected.some((item) => item.result_version_id === id)
        ? current.selected.filter((item) => item.result_version_id !== id)
        : [...current.selected, selectionItem(result)];
      return { ...current, selected, resolved_result_version_ids: [] };
    });
    setSelection(next);
  };

  const clearSelection = (exit = false) => {
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      selected: [],
      resolved_result_version_ids: [],
    }));
    setSelection(next);
    if (exit) updateRoute({ selectionToken: "" });
  };

  const continueToDashboard = () => {
    navigateHash("analysis-dashboards", {
      selection_token: route.selectionToken,
      step: "check",
    });
  };

  const openInsightDialog = async () => {
    if (!selectedResults.length) return;
    setInsightOpen(true);
    setInsightState({
      loading: true,
      submitting: false,
      error: "",
      plan: null,
      models: [],
    });
    const ids = selectedResults.map((item) => item.result_version_id);
    const configRequest =
      typeof api.configs === "function" ? api.configs() : Promise.resolve([]);
    const preferenceRequest =
      typeof api.modelPreference === "function"
        ? api.modelPreference()
        : Promise.resolve(null);
    const [planResult, configResult, preferenceResult] = await Promise.allSettled([
      dashboardApi.dashboardPreflight({
        result_version_ids: ids,
        filters: {},
      }),
      configRequest,
      preferenceRequest,
    ]);
    const plan = planResult.status === "fulfilled" ? planResult.value : null;
    const configs = configResult.status === "fulfilled" ? configResult.value : [];
    const preference =
      preferenceResult.status === "fulfilled" ? preferenceResult.value : null;
    const models = insightModels(configs);
    const modelId = preferredInsightModel(configs, models, preference);
    const selectedModel = models.find((model) => model.id === modelId);
    setInsightForm({
      modelId,
      effort: preferredInsightEffort(selectedModel),
    });
    setInsightState({
      loading: false,
      submitting: false,
      error:
        planResult.status === "rejected"
          ? planResult.reason?.message || "无法读取本次分析范围"
          : "",
      plan,
      models,
    });
  };

  const submitInsight = async (event) => {
    event.preventDefault();
    if (!insightForm.modelId || insightState.plan?.ready !== true) return;
    setInsightState((current) => ({ ...current, submitting: true, error: "" }));
    try {
      const created = await dashboardApi.createInsightReportFromResults({
        result_version_ids: selectedResults.map((item) => item.result_version_id),
        filters: insightState.plan.filters ?? {},
        plan_hash: insightState.plan.plan_hash,
        model_id: insightForm.modelId,
        reasoning_effort: insightForm.effort,
      });
      clearSelection(false);
      setInsightOpen(false);
      notify?.("AI 洞察报告已加入生成队列");
      navigateHash("analysis-dashboards", {
        dashboard: created.dashboard.id,
        version: created.dashboard.version.version_id,
        tab: "report",
        report: created.report.id,
      });
    } catch (error) {
      setInsightState((current) => ({
        ...current,
        submitting: false,
        error: error.message,
      }));
    }
  };

  const createDashboardFromResult = (result) => {
    const token = createDashboardSelection(userId, {
      selected: [selectionItem(result)],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };

  const runPrimaryAction = (result) => {
    const policy = resultActionPolicy(result, { taskId: route.taskId });
    if (policy.primary.kind === "create-dashboard") {
      createDashboardFromResult(result);
      return;
    }
    if (policy.primary.kind === "repair-source") {
      navigateHash("analysis-tasks", {
        task_id: policy.primary.taskId,
        segment_id: route.segmentId,
      });
      return;
    }
    updateRoute({
      version: resultVersionId(result),
      tab: policy.primary.kind === "create-review" ? "history" : "records",
      action: policy.primary.kind === "create-review" ? "review" : "",
      recordPage: 1,
      problem: "",
      productName: "",
      productSku: "",
      orderId: "",
    });
  };

  useEffect(() => {
    setFilters({
      q: route.q,
      storeSite: route.storeSite,
      listing: route.listing,
      qualityStatus: route.qualityStatus,
    });
  }, [route.listing, route.q, route.qualityStatus, route.storeSite]);

  const query = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      q: route.q,
      store_site: route.storeSite,
      listing: route.listing,
      quality_status: route.qualityStatus,
    }),
    [
      route.listing,
      route.page,
      route.pageSize,
      route.q,
      route.qualityStatus,
      route.storeSite,
    ],
  );

  const load = useCallback(async () => {
    const generation = listGenerationRef.current + 1;
    listGenerationRef.current = generation;
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const value = await api.classificationResults(query, {
        signal: controller.signal,
      });
      if (listGenerationRef.current !== generation) return;
      setData(value);
      firstResultRef.current = value.items?.[0]?.version_id ?? "";
      setHasNewResults(false);
    } catch (loadError) {
      if (listGenerationRef.current === generation && loadError.name !== "AbortError") {
        setError(loadError.message);
      }
    } finally {
      if (listGenerationRef.current === generation) setLoading(false);
      if (listControllerRef.current === controller) {
        listControllerRef.current = null;
      }
    }
  }, [query]);

  useEffect(() => {
    const generation = listGenerationRef.current + 1;
    listGenerationRef.current = generation;
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    setLoading(true);
    setError("");
    api
      .classificationResults(query, { signal: controller.signal })
      .then((value) => {
        if (listGenerationRef.current !== generation) return;
        setData(value);
        firstResultRef.current = value.items?.[0]?.version_id ?? "";
        setHasNewResults(false);
      })
      .catch((loadError) => {
        if (
          listGenerationRef.current === generation &&
          loadError.name !== "AbortError"
        ) {
          setError(loadError.message);
        }
      })
      .finally(() => {
        if (listGenerationRef.current === generation) setLoading(false);
        if (listControllerRef.current === controller) {
          listControllerRef.current = null;
        }
      });
    return () => {
      if (listGenerationRef.current === generation) {
        listGenerationRef.current += 1;
      }
      listControllerRef.current?.abort();
      listControllerRef.current = null;
    };
  }, [query]);

  useEffect(() => {
    const generation = pollGenerationRef.current + 1;
    pollGenerationRef.current = generation;
    const timer = window.setInterval(() => {
      pollControllerRef.current?.abort();
      const controller = new AbortController();
      pollControllerRef.current = controller;
      api
        .classificationResults(query, { signal: controller.signal })
        .then((value) => {
          if (pollGenerationRef.current !== generation) return;
          const firstId = value.items?.[0]?.version_id ?? "";
          if (firstResultRef.current && firstId && firstId !== firstResultRef.current) {
            setHasNewResults(true);
          }
        })
        .catch((pollError) => {
          if (pollError.name !== "AbortError") return;
        })
        .finally(() => {
          if (pollControllerRef.current === controller) {
            pollControllerRef.current = null;
          }
        });
    }, 15000);
    return () => {
      if (pollGenerationRef.current === generation) {
        pollGenerationRef.current += 1;
      }
      window.clearInterval(timer);
      pollControllerRef.current?.abort();
      pollControllerRef.current = null;
    };
  }, [query]);

  const activeFilters = Boolean(
    route.q || route.storeSite || route.listing || route.qualityStatus,
  );
  const totalPages = Math.max(Math.ceil((data?.total ?? 0) / route.pageSize), 1);

  return (
    <div className="standard-page classification-results-page">
      <ResultWorkspaceNav
        active={route.qualityStatus === "review_required" ? "pending" : "results"}
      />
      <PageHeading
        eyebrow="不可变分类数据资产"
        title="分类结果池"
        description="每个已完成 Listing 独立发布结果版本，可在网页查看订单级分类与证据。"
        action={
          <button className="primary-button" onClick={startSelection}>
            <ChartBar size={18} /> 新建分析看板
          </button>
        }
      />

      {route.selectionToken && selectionIntent === "dashboard" && (
        <div className="dashboard-selection-notice" role="status">
          <div>
            <b>正在选择看板数据</b>
            <span>“需复核”版本也可加入；看板会自动排除待复核和已排除记录。</span>
          </div>
          <button
            className="text-button"
            onClick={() => updateRoute({ selectionToken: "" })}
          >
            退出选择
          </button>
        </div>
      )}

      {hasNewResults && (
        <div className="result-refresh-banner" role="status">
          <span>有新的 Listing 分类结果可用，当前列表未自动改变。</span>
          <button className="secondary-button" onClick={load}>
            刷新列表
          </button>
        </div>
      )}

      <section className="result-pool-filters" aria-label="分类结果筛选">
        <div className="result-pool-search">
          <MagnifyingGlass size={18} />
          <input
            aria-label="搜索分类结果"
            placeholder="搜索 Listing、产品名称或 SKU"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </div>
        <input
          aria-label="店铺或站点"
          placeholder="店铺/站点"
          value={filters.storeSite}
          onChange={(event) =>
            setFilters({ ...filters, storeSite: event.target.value })
          }
        />
        <input
          aria-label="Listing"
          placeholder="Listing"
          value={filters.listing}
          onChange={(event) => setFilters({ ...filters, listing: event.target.value })}
        />
        <select
          aria-label="结果质量"
          value={filters.qualityStatus}
          onChange={(event) =>
            setFilters({ ...filters, qualityStatus: event.target.value })
          }
        >
          <option value="">全部质量状态</option>
          <option value="ready">可用</option>
          <option value="review_required">需复核</option>
          <option value="unusable">不可用</option>
        </select>
        <button
          className="primary-button"
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          <FunnelSimple size={17} />
          筛选
        </button>
      </section>

      <section className="result-pool-card">
        {loading && !data && <InlineLoading label="正在读取分类结果…" />}
        {error && <ResultError message={error} onRetry={load} />}
        {!loading && !error && data?.items?.length === 0 && (
          <EmptyState
            icon={Package}
            title={activeFilters ? "没有符合条件的结果" : "结果池还是空的"}
            description={
              activeFilters
                ? "调整筛选条件后重新查询。"
                : "Listing 片段完成并发布后，会在这里形成不可变结果版本。"
            }
          />
        )}
        {data?.items?.length > 0 && !error && (
          <>
            {selectionIntent === "insight" && selectedResults.length > 0 && (
              <InsightSelectionBar
                selected={selectedResults}
                totals={selectedTotals}
                onCancel={() => clearSelection(true)}
                onGenerate={openInsightDialog}
              />
            )}
            <div
              className={`result-pool-table is-selecting ${loading ? "is-loading" : ""}`}
            >
              <div className="result-pool-head" role="row">
                <span>选择</span>
                <span>结果状态</span>
                <span>Listing / 店铺</span>
                <span>产品名称</span>
                <span>数据规模</span>
                <span>发布时间</span>
                <span>操作</span>
              </div>
              {data.items.map((result) => (
                <ResultPoolRow
                  key={result.version_id}
                  result={result}
                  selectable
                  selected={selectedIds.has(resultVersionId(result))}
                  onToggle={() => toggleSelection(result)}
                  onPrimary={() => runPrimaryAction(result)}
                  onOpen={() =>
                    updateRoute({
                      version: result.version_id,
                      recordPage: 1,
                      problem: "",
                      productName: "",
                      productSku: "",
                      orderId: "",
                    })
                  }
                />
              ))}
            </div>
            <Pagination
              page={route.page}
              pageSize={route.pageSize}
              total={data.total}
              totalPages={totalPages}
              onPage={(page) => updateRoute({ page })}
              onPageSize={(pageSize) => updateRoute({ page: 1, pageSize })}
            />
          </>
        )}
      </section>
      {route.selectionToken && selectionIntent === "dashboard" && (
        <DashboardSelectionBar
          selected={selectedResults}
          onClear={clearSelection}
          onContinue={continueToDashboard}
        />
      )}
      {insightOpen && (
        <InsightGenerationModal
          form={insightForm}
          onChange={setInsightForm}
          onClose={() => setInsightOpen(false)}
          onSubmit={submitInsight}
          models={insightState.models}
          loading={insightState.loading}
          submitting={insightState.submitting}
          error={
            insightState.error ||
            insightState.plan?.blockers?.[0]?.message ||
            (insightState.plan?.conflicts?.length
              ? "所选结果包含同一 Listing 的重复版本，请调整选择。"
              : "")
          }
          ready={insightState.plan?.ready === true}
          scopeLabel={
            selectedResults.length === 1
              ? `${selectedResults[0].listing || "未提供 Listing"} · ${
                  selectedResults[0].product_names?.[0] || "未提供产品名称"
                }`
              : `${selectedResults.length} 个分类结果版本`
          }
          includedRecords={Number(
            insightState.plan?.summary?.record_count ?? selectedTotals.records,
          )}
          unitCount={selectedTotals.units}
          pendingRecords={Number(
            insightState.plan?.summary?.pending_review_record_count || 0,
          )}
          excludedRecords={Number(
            insightState.plan?.summary?.excluded_record_count || 0,
          )}
        />
      )}
    </div>
  );
}

function ResultPoolRow({ result, onOpen, onPrimary, selectable, selected, onToggle }) {
  const names = productNames(result);
  const policy = resultActionPolicy(result);
  const disabledReason = policy.dashboardSelectable ? "" : policy.blockingReason;
  return (
    <article className={`result-pool-row ${selected ? "is-selected" : ""}`} role="row">
      {selectable && (
        <label className="result-selection-cell" title={disabledReason}>
          <input
            type="checkbox"
            aria-label={`选择 ${result.listing || "未提供 Listing"} 结果 v${result.version}`}
            checked={selected}
            disabled={Boolean(disabledReason)}
            onChange={onToggle}
          />
          {disabledReason && <small>{disabledReason}</small>}
        </label>
      )}
      <div className="result-state-cell">
        <span className={`result-quality-badge ${policy.state}`}>{policy.label}</span>
        <small>
          {policy.state === "needs_review"
            ? "可先建立已可用数据看板，也可继续复核"
            : `版本发布：${PUBLISH_LABELS[result.publish_status] ?? result.publish_status ?? "未提供"}`}
        </small>
      </div>
      <div className="result-listing-cell">
        <button className="text-button result-listing-link" onClick={onOpen}>
          {result.listing || "未提供 Listing"}
        </button>
        <span>{result.store_site || "未提供店铺/站点"}</span>
        <small>结果 v{result.version}</small>
      </div>
      <div className="result-product-cell">
        <b title={names.join("、")}>{names[0] || "未提供"}</b>
        {names.length > 1 && <span>另有 {names.length - 1} 个产品名称</span>}
        <small>产品信息 v{result.product_version}</small>
      </div>
      <div className="result-scale-cell">
        <b>{Number(result.record_count || 0).toLocaleString()} 条记录</b>
        <span>{Number(result.unit_count || 0).toLocaleString()} 个分类单元</span>
      </div>
      <div className="result-time-cell">
        <b>{formatTime(result.published_at || result.created_at)}</b>
        <span>{result.agent_family || "未提供智能体"}</span>
      </div>
      <div className="result-row-actions">
        <button
          className="secondary-button compact-button"
          disabled={policy.primary.disabled}
          title={policy.primary.disabled ? policy.blockingReason : ""}
          onClick={onPrimary}
        >
          {policy.primary.label}
          <CaretRight size={15} />
        </button>
        <a
          className="secondary-button compact-button"
          href={api.classificationResultDownloadUrl(result.version_id)}
        >
          <DownloadSimple size={15} />
          下载
        </a>
      </div>
    </article>
  );
}

function InsightSelectionBar({ selected, totals, onCancel, onGenerate }) {
  return (
    <div className="insight-selection-bar" role="status">
      <div>
        <b>已选 {selected.length} 项</b>
        <span>{totals.records.toLocaleString()} 条记录</span>
        <span>{totals.units.toLocaleString()} 个分类单元</span>
      </div>
      <button className="primary-button" onClick={onGenerate}>
        生成 AI 洞察
      </button>
      <button className="secondary-button" onClick={onCancel}>
        取消选择
      </button>
    </div>
  );
}

function DashboardSelectionBar({ selected, onClear, onContinue }) {
  const listingCount = new Set(
    selected.map((item) => `${item.store_site}::${item.listing}`),
  ).size;
  return (
    <aside className="dashboard-selection-bar" aria-label="看板数据选择">
      <div>
        <b>已选 {selected.length} 个结果版本</b>
        <span>覆盖 {listingCount} 个 Listing</span>
      </div>
      <button className="text-button" disabled={!selected.length} onClick={onClear}>
        清空
      </button>
      <button
        className="primary-button"
        disabled={!selected.length}
        onClick={onContinue}
      >
        检查并生成 <CaretRight size={17} />
      </button>
    </aside>
  );
}

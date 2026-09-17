import { useEffect, useMemo, useState } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import {
  ChartBar,
  FunnelSimple,
  MagnifyingGlass,
  Package,
} from "@phosphor-icons/react";

import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { dashboardApi } from "../../shared/api/dashboardApi";
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
import { Pagination, ResultError } from "./ClassificationResultCommon";
import {
  DashboardSelectionBar,
  InsightSelectionBar,
  ResultPoolRow,
} from "./ClassificationResultListParts";
import {
  isDashboardSelectable,
  resultActionPolicy,
  resultVersionId,
} from "./resultActionPolicy";
import { ResultWorkspaceNav } from "./ResultWorkspaceNav";
import { useClassificationResultListData } from "./useClassificationResultListData";

/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse} ClassificationResultVersion */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @typedef {import("../analysis-dashboards/analysisDashboardContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("../analysis-dashboards/analysisDashboardContracts").DashboardSelection} DashboardSelection */
/**
 * @typedef {object} InsightModel
 * @property {string} id
 * @property {string} [model_key]
 * @property {string} [display_name]
 * @property {string} [connection_id]
 * @property {string} [connection_name]
 * @property {string[]} [supported_efforts]
 */
/**
 * @typedef {object} InsightPlan
 * @property {boolean} ready
 * @property {string} plan_hash
 * @property {Record<string, string | string[] | null>} [filters]
 * @property {{ message: string }[]} [blockers]
 * @property {unknown[]} [conflicts]
 * @property {{ record_count?: number, pending_review_record_count?: number, excluded_record_count?: number }} [summary]
 */
/**
 * @typedef {object} InsightState
 * @property {boolean} loading
 * @property {boolean} submitting
 * @property {string} error
 * @property {InsightPlan | null} plan
 * @property {InsightModel[]} models
 */
/** @typedef {{ modelId: string, effort: string }} InsightForm */
/**
 * @typedef {object} ClassificationResultListProps
 * @property {ClassificationResultRoute} route
 * @property {(changes: Partial<ClassificationResultRoute>) => void} updateRoute
 * @property {(message: string, tone?: string) => void} notify
 * @property {string} userId
 */

/**
 * @param {DashboardSelectionItem[]} selected
 * @returns {{ records: number, units: number }}
 */
function selectedResultTotals(selected) {
  return selected.reduce(
    (total, item) => ({
      records: total.records + Number(item.record_count || 0),
      units: total.units + Number(item.unit_count || 0),
    }),
    { records: 0, units: 0 },
  );
}

/** @param {ClassificationResultListProps} props */
export function ClassificationResultList({ route, updateRoute, notify, userId }) {
  const [filters, setFilters] = useState({
    q: route.q,
    storeSite: route.storeSite,
    listing: route.listing,
    qualityStatus: route.qualityStatus,
  });
  const [selection, setSelection] = useState(
    /** @returns {DashboardSelection | null} */ () =>
      readDashboardSelection(userId, route.selectionToken),
  );
  const [insightOpen, setInsightOpen] = useState(false);
  const [insightState, setInsightState] = useState(
    /** @type {InsightState} */ ({
      loading: false,
      submitting: false,
      error: "",
      plan: null,
      models: [],
    }),
  );
  const [insightForm, setInsightForm] = useState(
    /** @type {InsightForm} */ ({
      modelId: "",
      effort: "high",
    }),
  );

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

  /** @param {ClassificationResultVersion} result */
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
    /** @param {DashboardSelection} current */
    const updateSelection = (current) => {
      const selected = current.selected.some((item) => item.result_version_id === id)
        ? current.selected.filter((item) => item.result_version_id !== id)
        : [...current.selected, selectionItem(result)];
      return { ...current, selected, resolved_result_version_ids: [] };
    };
    const next = updateDashboardSelection(
      userId,
      route.selectionToken,
      updateSelection,
    );
    setSelection(next);
  };

  const clearSelection = (exit = false) => {
    /** @param {DashboardSelection} current */
    const updateSelection = (current) => ({
      ...current,
      selected: [],
      resolved_result_version_ids: [],
    });
    const next = updateDashboardSelection(
      userId,
      route.selectionToken,
      updateSelection,
    );
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

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
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
        error: error instanceof Error ? error.message : "请求失败",
      }));
    }
  };

  /** @param {ClassificationResultVersion} result */
  const createDashboardFromResult = (result) => {
    const token = createDashboardSelection(userId, {
      selected: [selectionItem(result)],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };

  /** @param {ClassificationResultVersion} result */
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

  const { data, loading, error, hasNewResults, load } =
    useClassificationResultListData(query);

  const activeFilters = Boolean(
    route.q || route.storeSite || route.listing || route.qualityStatus,
  );
  const totalPages = Math.max(Math.ceil((data?.total ?? 0) / route.pageSize), 1);

  /** @param {number} page */
  const changePage = (page) => updateRoute({ page });
  /** @param {number} pageSize */
  const changePageSize = (pageSize) => updateRoute({ page: 1, pageSize });

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
        <label className="result-filter-field">
          <span>关键词</span>
          <Input
            aria-label="搜索分类结果"
            prefix={<MagnifyingGlass size={18} />}
            placeholder="搜索 Listing、产品名称或 SKU"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </label>
        <label className="result-filter-field">
          <span>店铺/站点</span>
          <Input
            aria-label="店铺或站点"
            placeholder="店铺/站点"
            value={filters.storeSite}
            onChange={(event) =>
              setFilters({ ...filters, storeSite: event.target.value })
            }
          />
        </label>
        <label className="result-filter-field">
          <span>Listing</span>
          <Input
            aria-label="Listing"
            placeholder="Listing"
            value={filters.listing}
            onChange={(event) =>
              setFilters({ ...filters, listing: event.target.value })
            }
          />
        </label>
        <label className="result-filter-field">
          <span>结果质量</span>
          <Select
            aria-label="结果质量"
            value={filters.qualityStatus}
            onChange={(qualityStatus) => setFilters({ ...filters, qualityStatus })}
            options={[
              { value: "", label: "全部质量状态" },
              { value: "ready", label: "可用" },
              { value: "review_required", label: "需复核" },
              { value: "unusable", label: "不可用" },
            ]}
          />
        </label>
        <Button
          type="primary"
          icon={<FunnelSimple size={17} />}
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          筛选
        </Button>
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
        {data && data.items.length > 0 && !error && (
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
              onPage={changePage}
              onPageSize={changePageSize}
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

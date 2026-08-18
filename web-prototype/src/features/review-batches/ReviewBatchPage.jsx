import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  CaretRight,
  ChartBar,
  CheckCircle,
  EyeSlash,
  FunnelSimple,
  ListChecks,
  MagnifyingGlass,
  PencilSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import { navigateHash, parseHash } from "../../app/hashRouter";
import {
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { ResultWorkspaceNav } from "../classification-results/ResultWorkspaceNav";
import { ReviewRecordDrawer, ReviewRecordRow } from "./ReviewRecordComponents";

const PAGE_SIZES = [20, 50, 100];
const BATCH_STATUS_LABELS = {
  draft: "复核中",
  in_review: "复核中",
  conflict: "存在冲突",
  published: "已发布",
};
function routeState(query) {
  const number = (key) => Number(query[key]);
  return {
    batchId: query.review_batch_id || "",
    resultVersionId: query.result_version_id || "",
    status: query.status || "",
    page: Math.max(number("page") || 1, 1),
    pageSize: PAGE_SIZES.includes(number("page_size")) ? number("page_size") : 20,
    listing: query.listing || "",
    productName: query.product_name || "",
    productSku: query.product_sku || "",
    orderId: query.order_id || "",
    q: query.q || "",
    taskId: query.task_id || "",
    segmentId: query.segment_id || "",
    returnTo: query.return_to || "",
  };
}

function writeRoute(route) {
  navigateHash("classification-results", {
    view: "reviews",
    review_batch_id: route.batchId,
    result_version_id: route.resultVersionId,
    status: route.status,
    page: route.page > 1 ? route.page : "",
    page_size: route.pageSize !== 20 ? route.pageSize : "",
    listing: route.listing,
    product_name: route.productName,
    product_sku: route.productSku,
    order_id: route.orderId,
    q: route.q,
    task_id: route.taskId,
    segment_id: route.segmentId,
    return_to: route.returnTo,
  });
}

function resultRouteQuery(route, versionId, tab = "") {
  const restored = route.returnTo ? parseHash(`#${route.returnTo}`).query : {};
  return {
    ...restored,
    result_version_id: versionId,
    review_batch_id: route.batchId,
    task_id: route.taskId || restored.task_id,
    segment_id: route.segmentId || restored.segment_id,
    tab,
    action: "",
  };
}

function itemId(item) {
  return item.id;
}

function pendingCount(batch) {
  return Number(batch?.pending_count ?? batch?.remaining_count ?? 0);
}

export function ReviewBatchPage({ route: appRoute, notify, userId }) {
  const route = routeState(appRoute.query);
  const updateRoute = useCallback(
    (changes) => writeRoute({ ...route, ...changes }),
    [route],
  );

  return route.batchId ? (
    <ReviewBatchWorkspace
      route={route}
      updateRoute={updateRoute}
      notify={notify}
      userId={userId}
    />
  ) : (
    <ReviewBatchList route={route} updateRoute={updateRoute} />
  );
}

function ReviewBatchList({ route, updateRoute }) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const [filters, setFilters] = useState({ q: route.q, status: route.status });
  const generationRef = useRef(0);
  const controllerRef = useRef(null);

  useEffect(() => {
    setFilters({ q: route.q, status: route.status });
  }, [route.q, route.status]);

  const query = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      status: route.status,
      base_result_version_id: route.resultVersionId,
      q: route.q,
    }),
    [route.page, route.pageSize, route.q, route.resultVersionId, route.status],
  );

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatches(query, {
        signal: controller.signal,
      });
      if (generationRef.current === generation) {
        setState({ loading: false, error: null, data });
      }
    } catch (error) {
      if (generationRef.current === generation && error.name !== "AbortError") {
        setState({ loading: false, error, data: null });
      }
    }
  }, [query]);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const items = state.data?.items ?? [];
  const totalPages = Math.max(
    Math.ceil(Number(state.data?.total || 0) / route.pageSize),
    1,
  );
  const openNeedsReviewResults = () =>
    navigateHash("classification-results", { quality_status: "review_required" });

  return (
    <div className="standard-page review-batch-page">
      <ResultWorkspaceNav active="reviews" />
      <PageHeading
        eyebrow="分类结果质量治理"
        title="复核记录"
        description="按批次处理需复核分类单元，完成后发布为新的不可变分类结果版本。"
      />
      <section className="review-batch-filters" aria-label="复核批次筛选">
        <div>
          <MagnifyingGlass size={18} />
          <input
            aria-label="搜索复核批次"
            placeholder="搜索 Listing、批次或创建人"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </div>
        <select
          aria-label="批次状态"
          value={filters.status}
          onChange={(event) => setFilters({ ...filters, status: event.target.value })}
        >
          <option value="">全部批次</option>
          <option value="draft">复核中</option>
          <option value="in_review">处理中</option>
          <option value="conflict">存在冲突</option>
          <option value="published">已发布</option>
        </select>
        <button
          className="primary-button"
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          <FunnelSimple size={17} /> 筛选
        </button>
      </section>

      <section className="review-batch-list-card">
        {state.loading && !state.data && <InlineLoading label="正在读取复核批次…" />}
        {state.error && <ReviewBatchError error={state.error} onRetry={load} />}
        {!state.loading && !state.error && items.length === 0 && (
          <EmptyState
            icon={ListChecks}
            title={route.q || route.status ? "没有符合条件的复核批次" : "暂无复核批次"}
            description={
              route.q || route.status
                ? "调整筛选条件后重新查询。"
                : "先从待复核的分类结果创建批次，再逐条确认或修改分类。"
            }
            action={
              !route.q && !route.status ? (
                <button className="primary-button" onClick={openNeedsReviewResults}>
                  查看待复核结果 <CaretRight size={16} />
                </button>
              ) : null
            }
          />
        )}
        {items.length > 0 && !state.error && (
          <>
            <div className={`review-batch-table ${state.loading ? "is-loading" : ""}`}>
              <div className="review-batch-table-head" role="row">
                <span>批次状态</span>
                <span>来源结果</span>
                <span>处理进度</span>
                <span>创建与更新</span>
                <span>操作</span>
              </div>
              {items.map((batch) => {
                const pending = pendingCount(batch);
                return (
                  <article className="review-batch-row" role="row" key={itemId(batch)}>
                    <div>
                      <span className={`review-batch-status ${batch.status}`}>
                        {BATCH_STATUS_LABELS[batch.status] ?? batch.status}
                      </span>
                      <small>修订 #{batch.revision ?? "—"}</small>
                    </div>
                    <div>
                      <b>{batch.listing || "未提供 Listing"}</b>
                      <span>分类结果 v{batch.base_version_no ?? "—"}</span>
                      <small>{batch.store_site || "未提供店铺/站点"}</small>
                    </div>
                    <div>
                      <b>
                        {Number(batch.resolved_count || 0).toLocaleString()} /{" "}
                        {Number(batch.record_count || 0).toLocaleString()}
                      </b>
                      <span>{pending ? `还剩 ${pending} 条` : "已全部处理"}</span>
                    </div>
                    <div>
                      <b>{batch.creator_name || "未提供创建人"}</b>
                      <span>{formatTime(batch.updated_at || batch.created_at)}</span>
                    </div>
                    <div>
                      <button
                        className="secondary-button compact-button"
                        onClick={() =>
                          updateRoute({
                            batchId: itemId(batch),
                            resultVersionId: batch.base_result_version_id,
                            status: "",
                            page: 1,
                            listing: "",
                            productName: "",
                            productSku: "",
                            orderId: "",
                            q: "",
                          })
                        }
                      >
                        进入批次 <CaretRight size={15} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
            <Pagination
              page={route.page}
              pageSize={route.pageSize}
              total={state.data.total}
              totalPages={totalPages}
              onPage={(page) => updateRoute({ page })}
              onPageSize={(pageSize) => updateRoute({ page: 1, pageSize })}
            />
          </>
        )}
      </section>
    </div>
  );
}

function ReviewBatchWorkspace({ route, updateRoute, notify, userId }) {
  const [batchState, setBatchState] = useState({
    loading: true,
    error: null,
    data: null,
  });
  const [recordsState, setRecordsState] = useState({
    loading: true,
    error: null,
    data: null,
  });
  const [labels, setLabels] = useState([]);
  const [filters, setFilters] = useState({
    q: route.q,
    status: route.status,
    listing: route.listing,
    productName: route.productName,
    productSku: route.productSku,
    orderId: route.orderId,
  });
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState("confirm");
  const [labelCode, setLabelCode] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [checkedIds, setCheckedIds] = useState([]);
  const [bulkAction, setBulkAction] = useState("");
  const [bulkLabelCode, setBulkLabelCode] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState("");
  const [conflict, setConflict] = useState(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishReason, setPublishReason] = useState("");
  const [publishError, setPublishError] = useState("");
  const [publishing, setPublishing] = useState(false);
  const batchGeneration = useRef(0);
  const recordGeneration = useRef(0);
  const batchController = useRef(null);
  const recordsController = useRef(null);

  useEffect(() => {
    setFilters({
      q: route.q,
      status: route.status,
      listing: route.listing,
      productName: route.productName,
      productSku: route.productSku,
      orderId: route.orderId,
    });
  }, [
    route.listing,
    route.orderId,
    route.productName,
    route.productSku,
    route.q,
    route.status,
  ]);

  const recordQuery = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      workflow_status: route.status,
      q: route.q,
      listing: route.listing,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
    }),
    [
      route.listing,
      route.orderId,
      route.page,
      route.pageSize,
      route.productName,
      route.productSku,
      route.q,
      route.status,
    ],
  );

  const loadBatch = useCallback(async () => {
    const generation = batchGeneration.current + 1;
    batchGeneration.current = generation;
    batchController.current?.abort();
    const controller = new AbortController();
    batchController.current = controller;
    setBatchState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatch(route.batchId, {
        signal: controller.signal,
      });
      if (batchGeneration.current === generation) {
        setBatchState({ loading: false, error: null, data });
      }
      return data;
    } catch (error) {
      if (batchGeneration.current === generation && error.name !== "AbortError") {
        setBatchState({ loading: false, error, data: null });
      }
      throw error;
    }
  }, [route.batchId]);

  const loadRecords = useCallback(async () => {
    const generation = recordGeneration.current + 1;
    recordGeneration.current = generation;
    recordsController.current?.abort();
    const controller = new AbortController();
    recordsController.current = controller;
    setRecordsState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatchRecords(route.batchId, recordQuery, {
        signal: controller.signal,
      });
      if (recordGeneration.current === generation) {
        setRecordsState({ loading: false, error: null, data });
      }
      return data;
    } catch (error) {
      if (recordGeneration.current === generation && error.name !== "AbortError") {
        setRecordsState({ loading: false, error, data: null });
      }
      throw error;
    }
  }, [recordQuery, route.batchId]);

  useEffect(() => {
    loadBatch().catch(() => {});
    return () => {
      batchGeneration.current += 1;
      batchController.current?.abort();
    };
  }, [loadBatch]);

  useEffect(() => {
    loadRecords().catch(() => {});
    return () => {
      recordGeneration.current += 1;
      recordsController.current?.abort();
    };
  }, [loadRecords]);

  useEffect(() => {
    const controller = new AbortController();
    reviewBatchApi
      .reviewTaxonomy({ signal: controller.signal })
      .then((value) => setLabels(value.labels ?? []))
      .catch((error) => {
        if (error.name !== "AbortError") notify(error.message, "error");
      });
    return () => controller.abort();
  }, [notify]);

  useEffect(() => {
    setSelected(null);
    setConflict(null);
    setCheckedIds([]);
  }, [route.batchId]);

  useEffect(() => {
    setCheckedIds([]);
  }, [recordQuery]);

  const batch = batchState.data;
  const records = recordsState.data;
  const pending = pendingCount(batch);
  const readOnly = batch?.status === "published";

  const openDerivedVersion = () => {
    navigateHash(
      "classification-results",
      resultRouteQuery(route, batch.derived_result_version_id),
    );
  };

  const createDashboardFromDerived = () => {
    const token = createDashboardSelection(userId, {
      selected: [
        selectionItem({
          version_id: batch.derived_result_version_id,
          version: batch.derived_version_no,
          result_state: "review-derived",
          quality_status: batch.derived_quality_status || "ready",
          store_site: batch.store_site,
          listing: batch.listing,
          record_count: batch.base_record_count || batch.record_count,
          unit_count: batch.base_unit_count || batch.unit_count,
          published_at: batch.derived_published_at,
        }),
      ],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };
  const totalPages = Math.max(
    Math.ceil(Number(records?.total || 0) / route.pageSize),
    1,
  );

  const openRecord = (record) => {
    const currentCode =
      record.classification?.primary_label_codes?.[0] ||
      record.classification?.problem_label_codes?.[0] ||
      "";
    setSelected(record);
    setMode("confirm");
    setLabelCode(currentCode);
    setReason("");
    setConflict(null);
  };

  const refreshConflict = async (error) => {
    const [latestBatch, latestPage] = await Promise.all([
      reviewBatchApi.reviewBatch(route.batchId),
      reviewBatchApi.reviewBatchRecords(route.batchId, recordQuery),
    ]);
    setBatchState({ loading: false, error: null, data: latestBatch });
    setRecordsState({ loading: false, error: null, data: latestPage });
    const serverRecord = latestPage.items?.find(
      (item) => itemId(item) === itemId(selected),
    );
    setConflict({ message: error.message, serverRecord });
  };

  const saveRecord = async (advance = false) => {
    if (!selected || !reason.trim()) return;
    const currentItems = records?.items ?? [];
    const currentIndex = currentItems.findIndex(
      (item) => itemId(item) === itemId(selected),
    );
    const nextPending = [
      ...currentItems.slice(currentIndex + 1),
      ...currentItems.slice(0, Math.max(currentIndex, 0)),
    ].find((item) => item.workflow_status === "pending");
    setSaving(true);
    try {
      const value = await reviewBatchApi.updateReviewBatchRecord(
        route.batchId,
        itemId(selected),
        {
          expected_revision: selected.revision,
          action: mode,
          label_code: mode === "modify" ? labelCode || null : null,
          reason: reason.trim(),
        },
      );
      setReason("");
      setConflict(null);
      await Promise.all([loadBatch(), loadRecords()]);
      if (advance && nextPending) {
        openRecord(nextPending);
      } else if (advance) {
        setSelected(null);
      } else {
        setSelected(value);
      }
      const messages = {
        confirm: "已确认原分类结果",
        modify: "分类结果修改已保存",
        exclude: "该记录已排除，不再进入语义分析和看板",
      };
      notify(messages[mode]);
    } catch (error) {
      if (error.status === 409) {
        try {
          await refreshConflict(error);
        } catch (refreshError) {
          notify(refreshError.message, "error");
        }
      } else {
        notify(error.message, "error");
      }
    } finally {
      setSaving(false);
    }
  };

  const openBulk = (action) => {
    setBulkAction(action);
    setBulkLabelCode("");
    setBulkReason("");
    setBulkError("");
  };

  const saveBulk = async () => {
    const selectedRecords = (records?.items ?? []).filter((record) =>
      checkedIds.includes(itemId(record)),
    );
    if (!selectedRecords.length || !bulkReason.trim()) return;
    setBulkSaving(true);
    setBulkError("");
    try {
      await reviewBatchApi.updateReviewBatchRecords(route.batchId, {
        records: selectedRecords.map((record) => ({
          id: itemId(record),
          expected_revision: record.revision,
        })),
        action: bulkAction,
        label_code: bulkAction === "modify" ? bulkLabelCode || null : null,
        reason: bulkReason.trim(),
      });
      setBulkAction("");
      setCheckedIds([]);
      await Promise.all([loadBatch(), loadRecords()]);
      notify(`已批量处理 ${selectedRecords.length} 条复核记录`);
    } catch (error) {
      setBulkError(error.message);
      if (error.status === 409) {
        await Promise.all([loadBatch(), loadRecords()]);
      }
    } finally {
      setBulkSaving(false);
    }
  };

  const publish = async () => {
    if (!batch || pending > 0 || !publishReason.trim()) return;
    setPublishing(true);
    setPublishError("");
    try {
      const derived = await reviewBatchApi.publishReviewBatch(route.batchId, {
        expected_revision: batch.revision,
        reason: publishReason.trim(),
      });
      setPublishOpen(false);
      notify(`分类结果 v${derived.version} 已发布`);
      navigateHash(
        "classification-results",
        resultRouteQuery(route, derived.version_id, "history"),
      );
    } catch (error) {
      if (error.status === 409) {
        setPublishError(`${error.message}。已刷新批次，请重新确认后发布。`);
        try {
          await loadBatch();
        } catch {
          // 批次读取错误已由页面状态展示。
        }
      } else {
        setPublishError(error.message);
      }
    } finally {
      setPublishing(false);
    }
  };

  if (batchState.loading && !batch) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <InlineLoading label="正在读取复核批次…" />
      </div>
    );
  }

  if (batchState.error && !batch) {
    return (
      <div className="standard-page review-batch-page review-batch-stable-state">
        <ReviewBatchError error={batchState.error} onRetry={loadBatch} />
      </div>
    );
  }

  return (
    <div className="standard-page review-batch-page">
      <button
        className="text-button review-batch-back"
        onClick={() =>
          updateRoute({
            batchId: "",
            status: "",
            page: 1,
            listing: "",
            productName: "",
            productSku: "",
            orderId: "",
            q: "",
          })
        }
      >
        <ArrowLeft size={17} /> 返回复核批次列表
      </button>

      <header className="review-batch-workspace-header">
        <div>
          <span className={`review-batch-status ${batch.status}`}>
            {BATCH_STATUS_LABELS[batch.status] ?? batch.status}
          </span>
          <h1>{batch.listing || "分类结果"} 复核批次</h1>
          <p>
            来源分类结果 v{batch.base_version_no ?? "—"} · 创建人{" "}
            {batch.creator_name || "未提供"} · 批次修订 #{batch.revision}
          </p>
        </div>
        <div className="review-batch-header-actions">
          <button
            className="secondary-button"
            onClick={() =>
              navigateHash(
                "classification-results",
                resultRouteQuery(route, batch.base_result_version_id, "history"),
              )
            }
          >
            查看来源版本
          </button>
          {readOnly ? (
            <>
              <button className="primary-button" onClick={openDerivedVersion}>
                查看衍生版本 <CaretRight size={16} />
              </button>
              <button className="secondary-button" onClick={createDashboardFromDerived}>
                <ChartBar size={17} /> 创建分析看板
              </button>
            </>
          ) : (
            <button
              className="primary-button"
              disabled={pending > 0 || Number(batch.record_count || 0) === 0}
              title={
                Number(batch.record_count || 0) === 0
                  ? "该历史批次没有可处理记录，不能发布"
                  : pending > 0
                    ? `还剩 ${pending} 条需处理，全部处理后才能发布`
                    : ""
              }
              onClick={() => {
                setPublishReason("");
                setPublishError("");
                setPublishOpen(true);
              }}
            >
              {Number(batch.record_count || 0) === 0
                ? "无可处理记录"
                : pending > 0
                  ? `还剩 ${pending} 条需处理`
                  : "发布派生版本"}
            </button>
          )}
        </div>
      </header>

      <section className="review-batch-progress" aria-label="复核批次进度">
        <div>
          <span>批次记录</span>
          <b>{Number(batch.record_count || 0).toLocaleString()}</b>
        </div>
        <div>
          <span>已确认 / 修改</span>
          <b>{Number(batch.resolved_count || 0).toLocaleString()}</b>
        </div>
        <div>
          <span>已排除</span>
          <b>{Number(batch.excluded_count || 0).toLocaleString()}</b>
        </div>
        <div className={pending ? "has-pending" : "is-complete"}>
          <span>待处理</span>
          <b>{pending.toLocaleString()}</b>
        </div>
        <div>
          <span>最后更新</span>
          <b>{formatTime(batch.updated_at)}</b>
        </div>
      </section>

      {readOnly && (
        <div className="review-batch-readonly" role="status">
          <CheckCircle size={18} />
          此批次已发布为分类结果 v{batch.derived_version_no ?? "—"}，当前内容只读。
        </div>
      )}

      <section className="review-record-filters" aria-label="复核记录筛选">
        <div className="review-record-search">
          <MagnifyingGlass size={17} />
          <input
            aria-label="搜索复核记录"
            placeholder="搜索评论、分类或业务字段"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </div>
        <select
          aria-label="处理状态"
          value={filters.status}
          onChange={(event) => setFilters({ ...filters, status: event.target.value })}
        >
          <option value="">全部记录</option>
          <option value="pending">待处理</option>
          <option value="resolved">已处理</option>
          <option value="excluded">已排除</option>
        </select>
        <input
          aria-label="筛选 Listing"
          placeholder="Listing"
          value={filters.listing}
          onChange={(event) => setFilters({ ...filters, listing: event.target.value })}
        />
        <input
          aria-label="筛选产品名称"
          placeholder="产品名称"
          value={filters.productName}
          onChange={(event) =>
            setFilters({ ...filters, productName: event.target.value })
          }
        />
        <input
          aria-label="筛选产品SKU"
          placeholder="产品SKU"
          value={filters.productSku}
          onChange={(event) =>
            setFilters({ ...filters, productSku: event.target.value })
          }
        />
        <input
          aria-label="筛选 order-id"
          placeholder="order-id"
          value={filters.orderId}
          onChange={(event) => setFilters({ ...filters, orderId: event.target.value })}
        />
        <button
          className="primary-button"
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          筛选
        </button>
      </section>

      {!readOnly && checkedIds.length > 0 && (
        <section className="review-bulk-toolbar" aria-label="批量复核操作">
          <b>已选择 {checkedIds.length} 条待处理记录</b>
          <div>
            <button className="secondary-button" onClick={() => openBulk("confirm")}>
              <CheckCircle size={17} /> 批量确认
            </button>
            <button className="secondary-button" onClick={() => openBulk("modify")}>
              <PencilSimple size={17} /> 批量修改分类
            </button>
            <button className="secondary-button" onClick={() => openBulk("exclude")}>
              <EyeSlash size={17} /> 批量排除
            </button>
            <button className="text-button" onClick={() => setCheckedIds([])}>
              取消选择
            </button>
          </div>
        </section>
      )}

      <section className="review-record-card">
        {recordsState.loading && !records && (
          <InlineLoading label="正在读取复核记录…" />
        )}
        {recordsState.error && (
          <ReviewBatchError error={recordsState.error} onRetry={loadRecords} />
        )}
        {!recordsState.loading &&
          !recordsState.error &&
          records?.items?.length === 0 && (
            <EmptyState
              icon={ListChecks}
              title="当前条件没有复核记录"
              description="调整处理状态或业务字段后重新查询。"
            />
          )}
        {records?.items?.length > 0 && !recordsState.error && (
          <>
            <div
              className={`review-record-table ${!readOnly ? "is-selectable" : ""} ${recordsState.loading ? "is-loading" : ""}`}
            >
              <div className="review-record-table-head" role="row">
                {!readOnly && (
                  <label className="review-record-checkbox">
                    <input
                      type="checkbox"
                      aria-label="选择本页待处理记录"
                      checked={
                        records.items.some(
                          (record) => record.workflow_status === "pending",
                        ) &&
                        records.items
                          .filter((record) => record.workflow_status === "pending")
                          .every((record) => checkedIds.includes(itemId(record)))
                      }
                      onChange={(event) => {
                        const pageIds = records.items
                          .filter((record) => record.workflow_status === "pending")
                          .map(itemId);
                        setCheckedIds(event.target.checked ? pageIds : []);
                      }}
                    />
                  </label>
                )}
                <span>order-id / 产品名称</span>
                <span>Listing / 产品SKU</span>
                <span>退货SKU（MSKU）</span>
                <span>分类结果</span>
                <span>状态 / 操作</span>
              </div>
              {records.items.map((record) => (
                <ReviewRecordRow
                  key={itemId(record)}
                  record={record}
                  selectionEnabled={!readOnly}
                  selectable={!readOnly && record.workflow_status === "pending"}
                  checked={checkedIds.includes(itemId(record))}
                  onCheck={(checked) =>
                    setCheckedIds((current) =>
                      checked
                        ? [...current, itemId(record)]
                        : current.filter((id) => id !== itemId(record)),
                    )
                  }
                  onOpen={() => openRecord(record)}
                />
              ))}
            </div>
            <Pagination
              page={route.page}
              pageSize={route.pageSize}
              total={records.total}
              totalPages={totalPages}
              onPage={(page) => updateRoute({ page })}
              onPageSize={(pageSize) => updateRoute({ page: 1, pageSize })}
            />
          </>
        )}
      </section>

      {selected && (
        <ReviewRecordDrawer
          record={selected}
          readOnly={readOnly}
          labels={labels}
          mode={mode}
          labelCode={labelCode}
          reason={reason}
          conflict={conflict}
          saving={saving}
          onMode={setMode}
          onLabelCode={setLabelCode}
          onReason={setReason}
          onSave={() => saveRecord(false)}
          onSaveAndNext={() => saveRecord(true)}
          onClose={() => setSelected(null)}
          onUseServer={() => {
            if (!conflict?.serverRecord) return;
            openRecord(conflict.serverRecord);
          }}
          onContinueWithServer={() => {
            if (!conflict?.serverRecord) return;
            setSelected(conflict.serverRecord);
            setConflict(null);
          }}
        />
      )}

      {publishOpen && (
        <Modal
          eyebrow="发布复核结果"
          title="生成新的分类结果版本"
          onClose={() => !publishing && setPublishOpen(false)}
        >
          <div className="review-publish-modal">
            <p>
              已确认或修改 {Number(batch.resolved_count || 0).toLocaleString()} 条，
              已排除 {Number(batch.excluded_count || 0).toLocaleString()} 条。
              发布会保留全部原始记录与审计轨迹；排除记录不进入语义分析和看板指标。
            </p>
            <label>
              发布原因
              <textarea
                rows="4"
                required
                value={publishReason}
                onChange={(event) => setPublishReason(event.target.value)}
                placeholder="必填：说明本次复核版本的发布原因"
              />
            </label>
            {publishError && (
              <div className="review-conflict-message" role="alert">
                <WarningCircle size={18} /> {publishError}
              </div>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                disabled={publishing}
                onClick={() => setPublishOpen(false)}
              >
                取消
              </button>
              <button
                className="primary-button"
                disabled={publishing || !publishReason.trim()}
                onClick={publish}
              >
                {publishing ? "正在发布…" : "确认生成新版本"}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {bulkAction && (
        <Modal
          eyebrow="批量复核"
          title={
            {
              confirm: "批量确认原结果",
              modify: "批量修改分类",
              exclude: "批量排除记录",
            }[bulkAction]
          }
          onClose={() => !bulkSaving && setBulkAction("")}
        >
          <div className="review-publish-modal">
            <p>本次将处理 {checkedIds.length} 条待处理记录。</p>
            {bulkAction === "exclude" && (
              <div className="review-exclude-note" role="status">
                <EyeSlash size={18} />
                排除后仍保留原始记录和操作记录，但不纳入语义分析及看板指标。
              </div>
            )}
            {bulkAction === "modify" && (
              <label>
                修改为
                <select
                  aria-label="批量修改分类标签"
                  value={bulkLabelCode}
                  onChange={(event) => setBulkLabelCode(event.target.value)}
                >
                  <option value="">请选择分类标签</option>
                  {labels.map((label) => (
                    <option key={label.code} value={label.code}>
                      {label.name} · {label.code}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              处理原因
              <textarea
                rows="4"
                required
                value={bulkReason}
                onChange={(event) => setBulkReason(event.target.value)}
                placeholder="必填：说明本次批量处理的判断依据"
              />
            </label>
            {bulkError && (
              <div className="review-conflict-message" role="alert">
                <WarningCircle size={18} /> {bulkError}
              </div>
            )}
            <div className="modal-actions">
              <button
                className="secondary-button"
                disabled={bulkSaving}
                onClick={() => setBulkAction("")}
              >
                取消
              </button>
              <button
                className="primary-button"
                disabled={
                  bulkSaving ||
                  !bulkReason.trim() ||
                  (bulkAction === "modify" && !bulkLabelCode)
                }
                onClick={saveBulk}
              >
                {bulkSaving ? "正在处理…" : `确认处理 ${checkedIds.length} 条`}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Pagination({ page, pageSize, total, totalPages, onPage, onPageSize }) {
  return (
    <div className="result-pagination">
      <span>共 {Number(total || 0).toLocaleString()} 条</span>
      <label>
        每页
        <select
          aria-label="每页数量"
          value={pageSize}
          onChange={(event) => onPageSize(Number(event.target.value))}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button compact-button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        上一页
      </button>
      <b>
        {page} / {totalPages}
      </b>
      <button
        className="secondary-button compact-button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        下一页
      </button>
    </div>
  );
}

function ReviewBatchError({ error, onRetry }) {
  const serviceUnavailable = error?.status === 404;
  return (
    <div className="review-batch-error" role="alert">
      <WarningCircle size={24} />
      <div>
        <b>复核批次读取失败</b>
        <p>
          {serviceUnavailable
            ? "新版复核服务尚不可用，请稍后重新加载"
            : error?.message || "暂时无法读取复核批次"}
        </p>
        {serviceUnavailable && error?.message && (
          <details>
            <summary>查看技术详情</summary>
            <code>{error.message}</code>
          </details>
        )}
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}

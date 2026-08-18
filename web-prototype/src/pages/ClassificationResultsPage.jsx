import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  CaretRight,
  ChartBar,
  DownloadSimple,
  ListChecks,
  MagnifyingGlass,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../api";
import { navigateHash, useHashRoute } from "../app/hashRouter";
import { EmptyState, InlineLoading } from "../components/SharedUi";
import { ResultVersionReviewPanel } from "../features/review-batches/ResultVersionReviewPanel";
import {
  createDashboardSelection,
  selectionItem,
} from "../features/analysis-dashboards/dashboardSelectionStorage";
import {
  resultActionPolicy,
  resultState,
  resultStateLabel,
} from "../features/classification-results/resultActionPolicy";
import { ClassificationResultList } from "../features/classification-results/ClassificationResultList";
import {
  Pagination,
  ResultError,
} from "../features/classification-results/ClassificationResultCommon";
import {
  PUBLISH_LABELS,
  RESULT_PAGE_SIZES,
} from "../features/classification-results/classificationResultConstants";
import { ReviewBatchPage } from "../features/review-batches/ReviewBatchPage";
import { formatTime } from "../lib/presentation";

function routeState(query) {
  const number = (key) => Number(query[key]);
  return {
    version: query.result_version_id || query.version || "",
    page: Math.max(number("page") || 1, 1),
    recordPage: Math.max(number("record_page") || 1, 1),
    pageSize: RESULT_PAGE_SIZES.includes(number("page_size"))
      ? number("page_size")
      : 20,
    q: query.q || "",
    storeSite: query.store_site || "",
    listing: query.listing || "",
    qualityStatus: query.quality_status || "",
    problem: query.problem || "",
    productName: query.product_name || "",
    productSku: query.product_sku || "",
    orderId: query.order_id || "",
    view: query.view === "reviews" ? "reviews" : "results",
    tab: query.tab === "history" ? "history" : "records",
    selectionToken: query.selection_token || "",
    taskId: query.task_id || "",
    segmentId: query.segment_id || "",
    reviewBatchId: query.review_batch_id || "",
    action: query.action || "",
  };
}

function writeRoute(route) {
  const values = {
    result_version_id: route.version,
    page: route.page > 1 ? route.page : "",
    record_page: route.recordPage > 1 ? route.recordPage : "",
    page_size: route.pageSize !== 20 ? route.pageSize : "",
    q: route.q,
    store_site: route.storeSite,
    listing: route.listing,
    quality_status: route.qualityStatus,
    problem: route.problem,
    product_name: route.productName,
    product_sku: route.productSku,
    order_id: route.orderId,
    tab: route.tab === "history" ? "history" : "",
    selection_token: route.selectionToken,
    task_id: route.taskId,
    segment_id: route.segmentId,
    review_batch_id: route.reviewBatchId,
    action: route.action,
  };
  navigateHash("classification-results", values);
}

export function ClassificationResultsPage({ notify, route: appRoute, userId }) {
  if (!appRoute) {
    return <StandaloneClassificationResultsPage notify={notify} userId={userId} />;
  }
  return (
    <ClassificationResultsContent notify={notify} appRoute={appRoute} userId={userId} />
  );
}

function StandaloneClassificationResultsPage({ notify, userId }) {
  const { route: hashRoute } = useHashRoute();
  return (
    <ClassificationResultsContent
      notify={notify}
      appRoute={hashRoute}
      userId={userId}
    />
  );
}

function ClassificationResultsContent({ notify, appRoute, userId }) {
  const route = routeState(appRoute.query);

  const updateRoute = useCallback(
    (changes) => writeRoute({ ...route, ...changes }),
    [route],
  );

  if (route.view === "reviews") {
    return <ReviewBatchPage route={appRoute} notify={notify} userId={userId} />;
  }

  return route.version ? (
    <ClassificationResultDetail
      route={route}
      updateRoute={updateRoute}
      notify={notify}
      userId={userId}
    />
  ) : (
    <ClassificationResultList
      route={route}
      updateRoute={updateRoute}
      notify={notify}
      userId={userId}
    />
  );
}

function ClassificationResultDetail({ route, updateRoute, notify, userId }) {
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [records, setRecords] = useState(null);
  const [drilldowns, setDrilldowns] = useState({
    problem: [],
    product_name: [],
    product_sku: [],
  });
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [orderInput, setOrderInput] = useState(route.orderId);
  const evidenceTriggerRef = useRef(null);
  const closeEvidence = useCallback(() => setSelectedRecord(null), []);

  const createDashboardFromResult = () => {
    const token = createDashboardSelection(userId, {
      selected: [selectionItem(result)],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };

  const openOrderRecords = () => {
    updateRoute({ tab: "records", action: "" });
    window.setTimeout(
      () => document.getElementById("classification-order-records")?.scrollIntoView(),
      0,
    );
  };

  useEffect(() => setOrderInput(route.orderId), [route.orderId]);
  useEffect(
    () => setSelectedRecord(null),
    [route.orderId, route.problem, route.productName, route.productSku, route.version],
  );

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      api.classificationResult(route.version, { signal: controller.signal }),
      api.classificationResultSummary(route.version, { signal: controller.signal }),
    ])
      .then(([version, versionSummary]) => {
        if (!active) return;
        setResult(version);
        setSummary(versionSummary);
      })
      .catch((loadError) => {
        if (active && loadError.name !== "AbortError") setError(loadError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [route.version]);

  const detailQuery = useMemo(
    () => ({
      page: route.recordPage,
      page_size: route.pageSize,
      problem: route.problem,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
    }),
    [
      route.orderId,
      route.pageSize,
      route.problem,
      route.productName,
      route.productSku,
      route.recordPage,
    ],
  );

  useEffect(() => {
    if (route.tab === "history") {
      setRecordsLoading(false);
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setRecordsLoading(true);
    Promise.all([
      api.classificationResultRecords(route.version, detailQuery, {
        signal: controller.signal,
      }),
      api.classificationResultDrilldown(
        route.version,
        "problem",
        { page: 1, page_size: 100 },
        { signal: controller.signal },
      ),
      api.classificationResultDrilldown(
        route.version,
        "product_name",
        { page: 1, page_size: 100, problem: route.problem },
        { signal: controller.signal },
      ),
      api.classificationResultDrilldown(
        route.version,
        "product_sku",
        {
          page: 1,
          page_size: 100,
          problem: route.problem,
          product_name: route.productName,
        },
        { signal: controller.signal },
      ),
    ])
      .then(([recordPage, problems, names, skus]) => {
        if (!active) return;
        setRecords(recordPage);
        setDrilldowns({
          problem: problems.items ?? [],
          product_name: names.items ?? [],
          product_sku: skus.items ?? [],
        });
      })
      .catch((loadError) => {
        if (active && loadError.name !== "AbortError") {
          notify(loadError.message, "error");
        }
      })
      .finally(() => {
        if (active) setRecordsLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [detailQuery, notify, route.productName, route.problem, route.tab, route.version]);

  if (loading && !result) {
    return (
      <div className="standard-page classification-results-page">
        <InlineLoading label="正在读取分类结果详情…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button"
          onClick={() => updateRoute({ version: "" })}
        >
          <ArrowLeft size={17} /> 返回结果池
        </button>
        <ResultError message={error} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  const totalPages = Math.max(Math.ceil((records?.total ?? 0) / route.pageSize), 1);
  const readyRecords = summary?.quality?.find(
    (item) => item.quality_status === "ready",
  )?.record_count;
  const reviewRecords = summary?.quality?.find((item) =>
    ["review_required", "needs_review"].includes(item.quality_status),
  )?.record_count;
  const policy = resultActionPolicy(result, {
    taskId: route.taskId,
    activeBatch: result.review_batch_id
      ? { id: result.review_batch_id, status: result.review_batch_status || "draft" }
      : null,
  });
  const allNeedReviewWithoutProblems =
    policy.state === "needs_review" &&
    !recordsLoading &&
    drilldowns.problem.length === 0 &&
    Number(reviewRecords || result.record_count || 0) > 0;

  const runPrimaryAction = () => {
    if (policy.primary.kind === "create-dashboard") {
      createDashboardFromResult();
      return;
    }
    if (policy.primary.kind === "enter-review") {
      navigateHash("classification-results", {
        view: "reviews",
        review_batch_id: policy.primary.reviewBatchId,
        result_version_id: result.version_id,
        task_id: route.taskId || result.source_task_id,
        segment_id: route.segmentId || result.source_segment_id,
        listing: route.listing,
      });
      return;
    }
    if (policy.primary.kind === "create-review") {
      updateRoute({ tab: "history", action: "review" });
      return;
    }
    if (policy.primary.kind === "repair-source") {
      navigateHash("analysis-tasks", {
        task_id: policy.primary.taskId,
        segment_id: route.segmentId,
      });
      return;
    }
    openOrderRecords();
  };

  return (
    <div className="standard-page classification-results-page result-detail-page">
      <button
        className="text-button result-back-button"
        onClick={() =>
          updateRoute({
            version: "",
            recordPage: 1,
            problem: "",
            productName: "",
            productSku: "",
            orderId: "",
          })
        }
      >
        <ArrowLeft size={17} /> 返回分类结果池
      </button>

      <header className="result-detail-header">
        <div>
          <span className={`result-quality-badge ${policy.state}`}>{policy.label}</span>
          <span className="result-publish-note">
            版本发布：
            {PUBLISH_LABELS[result.publish_status] ?? result.publish_status ?? "未提供"}
          </span>
          <h1>{result.listing || "未提供 Listing"} 分类结果</h1>
          <p>
            {result.store_site || "未提供店铺/站点"} · 结果 v{result.version} · 产品信息
            v{result.product_version} · {formatTime(result.published_at)}
          </p>
        </div>
        <div className="result-detail-actions">
          <button
            className="primary-button"
            disabled={policy.primary.disabled}
            title={policy.primary.disabled ? policy.blockingReason : ""}
            onClick={runPrimaryAction}
          >
            {policy.primary.kind === "create-dashboard" ? (
              <ChartBar size={18} />
            ) : (
              <ListChecks size={18} />
            )}
            {policy.primary.label}
          </button>
          {policy.secondary?.kind === "create-dashboard" && (
            <button
              className="secondary-button"
              disabled={policy.secondary.disabled}
              title={policy.secondary.disabled ? policy.blockingReason : ""}
              onClick={createDashboardFromResult}
            >
              <ChartBar size={18} /> {policy.secondary.label}
            </button>
          )}
          {policy.secondary?.kind === "view-records" && (
            <button className="secondary-button" onClick={openOrderRecords}>
              {policy.secondary.label}
            </button>
          )}
          <a
            className="secondary-button"
            href={api.classificationResultDownloadUrl(result.version_id)}
          >
            <DownloadSimple size={18} /> 下载当前版本
          </a>
        </div>
      </header>

      {policy.blockingReason && (
        <div className={`result-action-guidance is-${policy.state}`} role="status">
          <WarningCircle size={19} />
          <span>{policy.blockingReason}</span>
        </div>
      )}

      {allNeedReviewWithoutProblems && (
        <div className="result-action-guidance is-needs-review" role="status">
          <ListChecks size={19} />
          <span>
            尚未形成问题标签；当前{" "}
            {Number(reviewRecords || result.record_count).toLocaleString()}{" "}
            条均需复核，完成复核并发布派生版本后可按问题下钻。
          </span>
        </div>
      )}

      <nav className="result-detail-tabs" aria-label="分类结果详情">
        <button
          className={route.tab === "records" ? "active" : ""}
          onClick={() => updateRoute({ tab: "records" })}
        >
          分类数据
        </button>
        <button
          className={route.tab === "history" ? "active" : ""}
          onClick={() => updateRoute({ tab: "history" })}
        >
          版本历史与复核
        </button>
      </nav>

      {route.tab === "history" ? (
        <ResultVersionReviewPanel
          result={result}
          notify={notify}
          requestedAction={route.action}
          routeContext={{
            ...route,
            taskId: route.taskId || result.source_task_id,
            segmentId: route.segmentId || result.source_segment_id,
          }}
          onActionHandled={() => updateRoute({ action: "" })}
          onSelectVersion={(version) =>
            updateRoute({
              version,
              tab: "history",
              recordPage: 1,
              problem: "",
              productName: "",
              productSku: "",
              orderId: "",
            })
          }
        />
      ) : (
        <>
          <section className="result-summary-grid" aria-label="分类结果摘要">
            <SummaryMetric label="订单/退货记录" value={result.record_count} />
            <SummaryMetric label="分类单元" value={result.unit_count} />
            <SummaryMetric label="可用记录" value={readyRecords ?? 0} tone="green" />
            <SummaryMetric label="需复核记录" value={reviewRecords ?? 0} tone="amber" />
          </section>

          <section className="result-drilldown-card">
            <header>
              <div>
                <b>业务下钻</b>
                <span>
                  问题 → Listing → 产品名称 → 产品SKU → order-id → 分类结果与证据
                </span>
              </div>
              {(route.problem ||
                route.productName ||
                route.productSku ||
                route.orderId) && (
                <button
                  className="text-button"
                  onClick={() =>
                    updateRoute({
                      problem: "",
                      productName: "",
                      productSku: "",
                      orderId: "",
                      recordPage: 1,
                    })
                  }
                >
                  清除下钻条件
                </button>
              )}
            </header>
            <div className="drilldown-columns">
              <DrilldownColumn
                title="问题"
                items={drilldowns.problem}
                selected={route.problem}
                emptyTitle={
                  allNeedReviewWithoutProblems ? "尚未形成问题标签" : "暂无数据"
                }
                emptyDescription={
                  allNeedReviewWithoutProblems
                    ? `当前 ${Number(
                        reviewRecords || result.record_count,
                      ).toLocaleString()} 条记录需复核，完成复核并发布派生版本后，可按问题继续下钻。`
                    : ""
                }
                onSelect={(problem) =>
                  updateRoute({
                    problem,
                    productName: "",
                    productSku: "",
                    recordPage: 1,
                  })
                }
              />
              <DrilldownColumn
                title="产品名称"
                items={drilldowns.product_name}
                selected={route.productName}
                emptyLabel="未提供"
                onSelect={(productName) =>
                  updateRoute({ productName, productSku: "", recordPage: 1 })
                }
              />
              <DrilldownColumn
                title="产品SKU"
                items={drilldowns.product_sku}
                selected={route.productSku}
                emptyLabel="未提供"
                onSelect={(productSku) => updateRoute({ productSku, recordPage: 1 })}
              />
            </div>
          </section>

          <section className="result-record-card" id="classification-order-records">
            <header>
              <div>
                <b>订单级分类记录</b>
                <span>{Number(records?.total || 0).toLocaleString()} 条记录</span>
              </div>
              <div className="record-order-search">
                <input
                  aria-label="搜索 order-id"
                  placeholder="输入 order-id 精确查询"
                  value={orderInput}
                  onChange={(event) => setOrderInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      updateRoute({ orderId: orderInput.trim(), recordPage: 1 });
                    }
                  }}
                />
                <button
                  className="secondary-button"
                  onClick={() =>
                    updateRoute({ orderId: orderInput.trim(), recordPage: 1 })
                  }
                >
                  查询
                </button>
              </div>
            </header>

            {recordsLoading && !records && <InlineLoading label="正在读取订单记录…" />}
            {!recordsLoading && records?.items?.length === 0 && (
              <EmptyState
                icon={MagnifyingGlass}
                title="当前条件没有订单记录"
                description="调整问题、产品名称、产品SKU或order-id后重试。"
              />
            )}
            {records?.items?.length > 0 && (
              <>
                <div
                  className={`result-record-table ${recordsLoading ? "is-loading" : ""}`}
                >
                  <div className="result-record-head" role="row">
                    <span>order-id</span>
                    <span>退货SKU（MSKU）</span>
                    <span>产品名称 / 产品SKU</span>
                    <span>Amazon原因</span>
                    <span>分类结果</span>
                    <span>操作</span>
                  </div>
                  {records.items.map((record) => (
                    <ResultRecordRow
                      key={record.source_record_id}
                      record={record}
                      onOpen={(trigger) => {
                        evidenceTriggerRef.current = trigger;
                        setSelectedRecord(record);
                      }}
                    />
                  ))}
                </div>
                <Pagination
                  page={route.recordPage}
                  pageSize={route.pageSize}
                  total={records.total}
                  totalPages={totalPages}
                  onPage={(recordPage) => updateRoute({ recordPage })}
                  onPageSize={(pageSize) => updateRoute({ recordPage: 1, pageSize })}
                />
              </>
            )}
          </section>

          {selectedRecord && (
            <EvidenceDrawer
              record={selectedRecord}
              onClose={closeEvidence}
              returnFocusRef={evidenceTriggerRef}
            />
          )}
        </>
      )}
    </div>
  );
}

function SummaryMetric({ label, value, tone = "" }) {
  return (
    <div className={tone ? `is-${tone}` : ""}>
      <span>{label}</span>
      <b>{Number(value || 0).toLocaleString()}</b>
    </div>
  );
}

function DrilldownColumn({
  title,
  items,
  selected,
  onSelect,
  emptyLabel = "未标注",
  emptyTitle = "暂无数据",
  emptyDescription = "",
}) {
  return (
    <div className="drilldown-column">
      <b>{title}</b>
      <div>
        {items.length === 0 && (
          <span className="drilldown-empty">
            <b>{emptyTitle}</b>
            {emptyDescription && (
              <>
                <br />
                {emptyDescription}
              </>
            )}
          </span>
        )}
        {items.slice(0, 12).map((item) => {
          const value = item.value ?? "";
          const label = item.label_name || value || emptyLabel;
          return (
            <button
              key={`${title}-${value || "empty"}`}
              className={selected === value ? "active" : ""}
              onClick={() => onSelect(value)}
            >
              <span title={label}>{label}</span>
              <b>{Number(item.record_count || 0).toLocaleString()}</b>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ResultRecordRow({ record, onOpen }) {
  const problems = record.problem_labels ?? [];
  return (
    <article className="result-record-row" role="row">
      <div>
        <b>{record.order_id || "未提供"}</b>
        <span>{record.return_date || `源记录 ${record.source_row}`}</span>
      </div>
      <div>
        <b>{record.source_sku || "未提供"}</b>
        <span>匹配MSKU：{record.matched_msku || "未匹配"}</span>
      </div>
      <div>
        <b>{record.product_name || "未提供"}</b>
        <span>产品SKU：{record.product_sku || "未提供"}</span>
      </div>
      <div>
        <b>{record.reason || "未提供"}</b>
        <span>{record.comment || "没有退货评论"}</span>
      </div>
      <div>
        <span className={`result-quality-badge ${resultState(record)}`}>
          {resultStateLabel(record)}
        </span>
        <b>{problems.join("、") || "未形成问题标签"}</b>
      </div>
      <div className="result-row-actions">
        <button
          className="secondary-button compact-button"
          onClick={(event) => onOpen(event.currentTarget)}
        >
          查看证据
          <CaretRight size={15} />
        </button>
      </div>
    </article>
  );
}

function EvidenceDrawer({ record, onClose, returnFocusRef }) {
  const classification = record.classification ?? {};
  const units = classification.semantic_units ?? [];
  const unknowns = classification.unknown_semantics ?? [];
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
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
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
        aria-labelledby="evidence-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span id="evidence-drawer-title">分类结果与证据</span>
            <h2>{record.order_id || record.source_record_id}</h2>
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
          <DrawerField label="退货SKU（MSKU）" value={record.source_sku} />
          <DrawerField label="匹配MSKU" value={record.matched_msku} />
          <DrawerField label="产品SKU" value={record.product_sku} />
          <DrawerField
            label="产品匹配"
            value={record.product_match_status === "matched" ? "已匹配" : "未匹配"}
          />
        </section>

        <section className="drawer-section">
          <b>退货原文</b>
          <DrawerField label="Amazon原因" value={record.reason} />
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
          <DrawerField label="处理状态" value={record.processing_status} />
          <DrawerField
            label="复核原因"
            value={classification.review_reasons?.join("；")}
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
          {unknowns.map((unknown, index) => (
            <div className="evidence-unit is-unknown" key={`unknown-${index}`}>
              <span>未知语义</span>
              <blockquote>“{unknown.evidence || unknown.text || "未提供"}”</blockquote>
            </div>
          ))}
        </section>

        <section className="drawer-section drawer-lineage">
          <b>运行来源</b>
          <DrawerField label="模型" value={classification.model_name} />
          <DrawerField label="提示词版本" value={classification.prompt_version} />
          <DrawerField label="分类体系" value={classification.taxonomy_version} />
          <DrawerField label="classification_key" value={record.classification_key} />
          <DrawerField label="源记录ID" value={record.source_record_id} />
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

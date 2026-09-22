import { useCallback, useEffect, useRef, useState } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import {
  ArrowLeft,
  ChartBar,
  DownloadSimple,
  ListChecks,
  MagnifyingGlass,
  WarningCircle,
} from "@phosphor-icons/react";

import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageLoadingState } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { ResultVersionReviewPanel } from "../review-batches/ResultVersionReviewPanel";
import { Pagination, ResultError } from "./ClassificationResultCommon";
import {
  DrilldownColumn,
  ResultRecordRow,
  SummaryMetric,
} from "./ClassificationResultDetailParts";
import { PUBLISH_LABELS } from "./classificationResultConstants";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { resultActionPolicy } from "./resultActionPolicy";
import { useClassificationResultDetailData } from "./useClassificationResultDetailData";

/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} ClassificationResultGroup */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/**
 * @typedef {object} ClassificationResultDetailProps
 * @property {ClassificationResultRoute} route
 * @property {(changes: Partial<ClassificationResultRoute>) => void} updateRoute
 * @property {(message: string, tone?: string) => void} notify
 * @property {string} userId
 */

/** @param {ClassificationResultDetailProps} props */
export function ClassificationResultDetail({ route, updateRoute, notify, userId }) {
  const [selectedGroup, setSelectedGroup] = useState(
    /** @type {ClassificationResultGroup | null} */ (null),
  );
  const [orderInput, setOrderInput] = useState(route.orderId);
  const evidenceTriggerRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const closeEvidence = useCallback(() => setSelectedGroup(null), []);

  const createDashboardFromResult = () => {
    if (!result) return;
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
    () => setSelectedGroup(null),
    [route.orderId, route.problem, route.productName, route.productSku, route.version],
  );

  const {
    result,
    summary,
    records,
    drilldowns,
    loading,
    recordsLoading,
    error,
    retry,
  } = useClassificationResultDetailData({ route, notify });

  if (loading && !result) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button"
          onClick={() => updateRoute({ version: "" })}
        >
          <ArrowLeft size={17} /> 返回分类结果池
        </button>
        <PageLoadingState label="正在读取分类结果详情…" />
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
        <ResultError message={error} onRetry={retry} />
      </div>
    );
  }

  if (!result) return null;

  const isUserFeedback = result.analysis_context === "user_feedback";
  const totalPages = Math.max(Math.ceil((records?.total ?? 0) / route.pageSize), 1);
  const readyRecords = summary?.quality?.find(
    (item) => item.quality_status === "ready",
  )?.record_count;
  const reviewRecords = summary?.quality?.find((item) =>
    ["review_required", "needs_review"].includes(item.quality_status),
  )?.record_count;
  const excludedRecords = summary?.quality?.find(
    (item) => item.quality_status === "excluded",
  )?.record_count;
  const unusableRecords = summary?.quality?.find(
    (item) => item.quality_status === "unusable",
  )?.record_count;
  const modelErrorRecords = summary?.processing_statuses?.find(
    (item) => item.processing_status === "MODEL_ERROR",
  )?.record_count;
  const accountedRecords =
    Number(readyRecords || 0) +
    Number(reviewRecords || 0) +
    Number(excludedRecords || 0) +
    Number(unusableRecords || 0);
  const totalRecords = Number(result.record_count || 0);
  const reviewBatchId =
    typeof result.review_batch_id === "string" ? result.review_batch_id : "";
  const reviewBatchStatus =
    typeof result.review_batch_status === "string"
      ? result.review_batch_status
      : "draft";
  const policy = resultActionPolicy(result, {
    taskId: route.taskId,
    activeBatch: reviewBatchId
      ? { id: reviewBatchId, status: reviewBatchStatus }
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

  /** @param {string} version */
  const selectVersion = (version) =>
    updateRoute({
      version,
      tab: "history",
      recordPage: 1,
      problem: "",
      productName: "",
      productSku: "",
      orderId: "",
    });
  /** @param {string} problem */
  const selectProblem = (problem) =>
    updateRoute({
      problem,
      productName: "",
      productSku: "",
      recordPage: 1,
    });
  /** @param {string} productName */
  const selectProductName = (productName) =>
    updateRoute({ productName, productSku: "", recordPage: 1 });
  /** @param {string} productSku */
  const selectProductSku = (productSku) => updateRoute({ productSku, recordPage: 1 });
  /**
   * @param {ClassificationResultGroup} group
   * @returns {(trigger: HTMLButtonElement) => void}
   */
  const openEvidence = (group) => (trigger) => {
    evidenceTriggerRef.current = trigger;
    setSelectedGroup(group);
  };
  /** @param {number} recordPage */
  const changeRecordPage = (recordPage) => updateRoute({ recordPage });
  /** @param {number} pageSize */
  const changePageSize = (pageSize) => updateRoute({ recordPage: 1, pageSize });

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
            v{result.product_version} ·{" "}
            {result.standard_name || result.agent_family || "历史分类逻辑"}
            {result.standard_version ? ` V${result.standard_version}` : ""} ·{" "}
            {formatTime(result.published_at)}
          </p>
        </div>
        <div className="result-detail-actions">
          <Button
            type="primary"
            disabled={policy.primary.disabled}
            title={policy.primary.disabled ? policy.blockingReason : ""}
            icon={
              policy.primary.kind === "create-dashboard" ? (
                <ChartBar size={18} />
              ) : (
                <ListChecks size={18} />
              )
            }
            onClick={runPrimaryAction}
          >
            {policy.primary.label}
          </Button>
          {policy.secondary?.kind === "create-dashboard" && (
            <Button
              disabled={policy.secondary.disabled}
              title={policy.secondary.disabled ? policy.blockingReason : ""}
              icon={<ChartBar size={18} />}
              onClick={createDashboardFromResult}
            >
              {policy.secondary.label}
            </Button>
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
          onSelectVersion={selectVersion}
        />
      ) : (
        <>
          <section className="result-summary-grid" aria-label="分类结果摘要">
            <SummaryMetric label="订单/退货记录" value={result.record_count} />
            <SummaryMetric label="分类单元" value={result.unit_count} />
            <SummaryMetric label="可用记录" value={readyRecords ?? 0} tone="green" />
            <SummaryMetric label="需复核记录" value={reviewRecords ?? 0} tone="amber" />
            <SummaryMetric label="已忽略记录" value={excludedRecords ?? 0} />
            <SummaryMetric
              label="不可用记录"
              value={unusableRecords ?? 0}
              note={`其中模型异常 ${Number(modelErrorRecords || 0).toLocaleString()} 条`}
              tone="red"
            />
          </section>
          <p
            className={`result-accounting-note ${accountedRecords === totalRecords ? "is-balanced" : "is-warning"}`}
            role="status"
          >
            记录对账：{totalRecords.toLocaleString()} ={" "}
            {Number(readyRecords || 0).toLocaleString()} 可用 +{" "}
            {Number(reviewRecords || 0).toLocaleString()} 需复核 +{" "}
            {Number(excludedRecords || 0).toLocaleString()} 已忽略 +{" "}
            {Number(unusableRecords || 0).toLocaleString()} 不可用
            {accountedRecords !== totalRecords &&
              `；仍有 ${Math.abs(totalRecords - accountedRecords).toLocaleString()} 条未对齐`}
          </p>

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
                title={summary?.hierarchy_problems?.length ? "问题层级" : "问题"}
                items={
                  summary?.hierarchy_problems?.length
                    ? summary.hierarchy_problems
                    : drilldowns.problem
                }
                limit={summary?.hierarchy_problems?.length ? Infinity : 12}
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
                onSelect={selectProblem}
              />
              <DrilldownColumn
                title="产品名称"
                items={drilldowns.product_name}
                selected={route.productName}
                emptyLabel="未提供"
                onSelect={selectProductName}
              />
              <DrilldownColumn
                title="产品SKU"
                items={drilldowns.product_sku}
                selected={route.productSku}
                emptyLabel="未提供"
                onSelect={selectProductSku}
              />
            </div>
          </section>

          <section className="result-record-card" id="classification-order-records">
            <header>
              <div>
                <b>{isUserFeedback ? "用户反馈记录" : "订单级分类记录"}</b>
                <span>
                  {Number(records?.total || 0).toLocaleString()} 组反馈 · 关联
                  {Number(records?.source_total || 0).toLocaleString()} 条源明细
                </span>
              </div>
              <div className="record-order-search">
                <Input
                  aria-label="搜索 order-id"
                  placeholder="输入 order-id 精确查询"
                  value={orderInput}
                  onChange={(event) => setOrderInput(event.target.value)}
                  onPressEnter={() =>
                    updateRoute({ orderId: orderInput.trim(), recordPage: 1 })
                  }
                />
                <Button
                  onClick={() =>
                    updateRoute({ orderId: orderInput.trim(), recordPage: 1 })
                  }
                >
                  查询
                </Button>
              </div>
            </header>

            {recordsLoading && !records && <InlineLoading label="正在读取订单记录…" />}
            {!recordsLoading && records?.items?.length === 0 && (
              <EmptyState
                icon={MagnifyingGlass}
                title={isUserFeedback ? "当前条件没有反馈记录" : "当前条件没有订单记录"}
                description="调整问题、产品名称、产品SKU或order-id后重试。"
              />
            )}
            {records && records.items.length > 0 && (
              <>
                <div
                  className={`result-record-table ${recordsLoading ? "is-loading" : ""}`}
                >
                  <div className="result-record-head" role="row">
                    <span>{isUserFeedback ? "记录ID / 日期" : "order-id"}</span>
                    <span>
                      {isUserFeedback ? "来源SKU（MSKU）" : "退货SKU（MSKU）"}
                    </span>
                    <span>产品名称 / 产品SKU</span>
                    <span>{isUserFeedback ? "反馈标题 / 正文" : "Amazon原因"}</span>
                    <span>{isUserFeedback ? "语义结果" : "分类结果"}</span>
                    <span>操作</span>
                  </div>
                  {records.items.map((group) => (
                    <ResultRecordRow
                      key={group.record.source_record_id}
                      group={group}
                      analysisContext={result.analysis_context}
                      onOpen={openEvidence(group)}
                    />
                  ))}
                </div>
                <Pagination
                  page={route.recordPage}
                  pageSize={route.pageSize}
                  total={records.total}
                  totalPages={totalPages}
                  onPage={changeRecordPage}
                  onPageSize={changePageSize}
                />
              </>
            )}
          </section>

          {selectedGroup && (
            <EvidenceDrawer
              group={selectedGroup}
              analysisContext={result.analysis_context}
              onClose={closeEvidence}
              returnFocusRef={evidenceTriggerRef}
            />
          )}
        </>
      )}
    </div>
  );
}

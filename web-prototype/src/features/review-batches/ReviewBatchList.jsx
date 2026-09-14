import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CaretRight,
  FunnelSimple,
  ListChecks,
  MagnifyingGlass,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import { ResultWorkspaceNav } from "../classification-results/ResultWorkspaceNav";
import { ReviewBatchError } from "./ReviewBatchError";
import { BATCH_STATUS_LABELS, pendingCount } from "./reviewBatchPresentation";

export function ReviewBatchList({ route, updateRoute }) {
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
        <label className="review-filter-field">
          <span>关键词</span>
          <div className="review-batch-search">
            <MagnifyingGlass size={18} />
            <input
              aria-label="搜索复核批次"
              placeholder="搜索 Listing、批次或创建人"
              value={filters.q}
              onChange={(event) => setFilters({ ...filters, q: event.target.value })}
            />
          </div>
        </label>
        <label className="review-filter-field">
          <span>批次状态</span>
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
        </label>
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
                  <article className="review-batch-row" role="row" key={batch.id}>
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
                            batchId: batch.id,
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

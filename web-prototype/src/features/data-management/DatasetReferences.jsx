import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useRef } from "react";
import useSWR from "swr";
import { useLoadingHeight } from "../../hooks/useLoadingHeight";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { errorMessage } from "../../shared/api/requestErrors";
import { ArrowClockwise, Database } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../../api";
import { CardHeading, EmptyState, InlineLoading } from "../../components/SharedUi";
import { DatasetReferenceTable } from "./DatasetReferenceTable";

/** @typedef {import("../../app/navigation").Navigate} Navigate */

/**
 * @param {{
 *   currentVersionId?: string,
 *   page: number,
 *   onRouteChange?: (changes: Record<string, string | number>) => void,
 *   onNavigate?: Navigate,
 * }} props
 */
export function DatasetReferences({
  currentVersionId,
  page,
  onRouteChange,
  onNavigate,
}) {
  const selectedVersionId = currentVersionId ?? "";
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const regionRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const {
    data = null,
    error,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(
    selectedVersionId ? ["data-assets", "references", selectedVersionId, page] : null,
    () =>
      runResultRequest(
        controllerRef,
        (signal) =>
          api.dataVersionReferences(
            selectedVersionId,
            { page, page_size: 20 },
            { signal },
          ),
        (value) => value,
      ),
    MANAGED_REFRESH_OPTIONS,
  );
  useDataRefresh(() => mutate(), {
    enabled: Boolean(selectedVersionId),
    loading: isLoading || isValidating,
    identity: `${currentVersionId}:${page}`,
  });
  const state = {
    data,
    loading: isLoading || isValidating,
    error: error ? errorMessage(error) : "",
  };
  const load = useCallback(
    () => mutate((current) => current, { revalidate: true, throwOnError: false }),
    [mutate],
  );
  useLoadingHeight(state.loading, regionRef);

  const total = Number(state.data?.total ?? 0);
  const pages = Math.max(Math.ceil(total / 20), 1);

  return (
    <section
      className="dataset-view-panel dataset-reference-panel"
      aria-busy={state.loading}
    >
      <CardHeading
        title="任务引用"
        action={
          <InlineLoading
            label="更新中…"
            compact
            active={state.loading && Boolean(data)}
          />
        }
      />
      <div ref={regionRef} className="loading-region">
        {state.loading && !data && (
          <InlineLoading scope="page" label="正在读取任务引用…" />
        )}
        {state.error && (
          <div className="plan-state error dataset-reference-error" role="alert">
            <div>
              <b>
                {data ? "任务引用更新失败，当前显示上一次数据" : "任务引用读取失败"}
              </b>
              <p>{state.error}</p>
            </div>
            <Button icon={<ArrowClockwise size={16} />} onClick={() => load()}>
              重新加载
            </Button>
          </div>
        )}
        {!state.loading && !state.error && data?.items.length === 0 && (
          <EmptyState
            icon={Database}
            title="尚未被任务引用"
            description="使用这份产品资料的任务会显示在这里。"
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <DatasetReferenceTable items={data.items} onNavigate={onNavigate} />
            <footer className="quality-pagination">
              <span>
                共 {total.toLocaleString()} 条 · 第 {page}/{pages} 页
              </span>
              <button
                className="secondary-button"
                disabled={page <= 1}
                onClick={() => onRouteChange?.({ reference_page: page - 1 })}
              >
                上一页
              </button>
              <button
                className="secondary-button"
                disabled={page >= pages}
                onClick={() => onRouteChange?.({ reference_page: page + 1 })}
              >
                下一页
              </button>
            </footer>
          </>
        )}
      </div>
    </section>
  );
}

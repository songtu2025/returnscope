import { useCallback, useRef } from "react";
import useSWR from "swr";
import { useLoadingHeight } from "../../hooks/useLoadingHeight";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { errorMessage } from "../../shared/api/requestErrors";
import { ArrowClockwise, ArrowRight, Database } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../../api";
import { CardHeading, EmptyState, InlineLoading } from "../../components/SharedUi";
import { STATUS_LABELS } from "../../constants";
import { formatTime } from "../../lib/presentation";

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
  );
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
        note="任务执行时保留启动时的输入资料"
        action={
          <InlineLoading
            label="更新中…"
            compact
            active={state.loading && Boolean(data)}
          />
        }
      />
      <div ref={regionRef} className="loading-region">
        {state.loading && !data && <InlineLoading label="正在读取任务引用…" />}
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
            <div className="dataset-reference-list">
              {data.items.map((item) => (
                <article key={`${item.task_id}-${item.reference_type}`}>
                  <span className="dataset-reference-role">
                    {item.reference_type === "returns" ? "退货明细" : "产品信息"}
                  </span>
                  <div>
                    <b>{item.title || `任务 #${item.task_id}`}</b>
                    <p>
                      {(item.status
                        ? /** @type {Record<string, string>} */ (STATUS_LABELS)[
                            item.status
                          ]
                        : undefined) ??
                        item.status ??
                        "未提供状态"}{" "}
                      · {item.owner?.name || "未提供所有者"} ·{" "}
                      {formatTime(item.created_at)}
                    </p>
                    <details>
                      <summary>任务输入资料</summary>
                      <SnapshotFields value={item.version_snapshot} />
                    </details>
                  </div>
                  <button
                    className="secondary-button"
                    onClick={() =>
                      onNavigate?.("analysis-tasks", { kind: "task", id: item.task_id })
                    }
                  >
                    查看任务
                    <ArrowRight size={15} />
                  </button>
                </article>
              ))}
            </div>
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

/** @param {{value?: Record<string, unknown>}} props */
function SnapshotFields({ value }) {
  const entries = Object.entries(value ?? {}).filter(
    ([key]) => !["version", "version_id"].includes(key),
  );
  if (!entries.length) return <p>未提供快照明细</p>;
  return (
    <dl className="snapshot-field-list">
      {entries.map(([key, fieldValue]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>
            {fieldValue && typeof fieldValue === "object"
              ? JSON.stringify(fieldValue)
              : String(fieldValue ?? "未提供")}
          </dd>
        </div>
      ))}
    </dl>
  );
}

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, ArrowRight, Database } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../../api";
import { CardHeading, EmptyState, InlineLoading } from "../../components/SharedUi";
import { STATUS_LABELS } from "../../constants";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("../../app/navigation").Navigate} Navigate */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetVersion} DatasetVersion */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetReferencePage} DatasetReferencePage */

/**
 * @param {{
 *   versions: DatasetVersion[],
 *   currentVersionId?: string,
 *   routeVersionId?: string,
 *   page: number,
 *   onRouteChange?: (changes: Record<string, string | number>) => void,
 *   onNavigate?: Navigate,
 * }} props
 */
export function DatasetReferences({
  versions,
  currentVersionId,
  routeVersionId,
  page,
  onRouteChange,
  onNavigate,
}) {
  const availableVersionIds = versions.map((item) =>
    String(item.id ?? item.version_id),
  );
  const selectedVersionId = availableVersionIds.includes(String(routeVersionId))
    ? String(routeVersionId)
    : String(currentVersionId ?? availableVersionIds[0] ?? "");
  const [state, setState] = useState(
    /** @type {{loading: boolean, error: string, data: DatasetReferencePage | null}} */ ({
      loading: true,
      error: "",
      data: null,
    }),
  );

  const load = useCallback(
    /** @param {AbortSignal} [signal] */
    async (signal) => {
      if (!selectedVersionId) {
        setState({ loading: false, error: "", data: null });
        return;
      }
      setState({ loading: true, error: "", data: null });
      try {
        const data = await api.dataVersionReferences(
          selectedVersionId,
          { page, page_size: 20 },
          { signal },
        );
        setState({ loading: false, error: "", data });
      } catch (error) {
        const requestError =
          error instanceof Error ? error : new Error("任务引用读取失败");
        if (requestError.name !== "AbortError") {
          setState({ loading: false, error: requestError.message, data: null });
        }
      }
    },
    [page, selectedVersionId],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const total = Number(state.data?.total ?? 0);
  const pages = Math.max(Math.ceil(total / 20), 1);

  return (
    <section className="dataset-view-panel dataset-reference-panel">
      <CardHeading title="任务引用" note="历史任务始终保留启动时固化的数据版本" />
      <div className="dataset-reference-toolbar">
        <label>
          数据版本
          <select
            value={selectedVersionId}
            onChange={(event) =>
              onRouteChange?.({
                tab: "references",
                reference_version: event.target.value,
                reference_page: 1,
              })
            }
          >
            {versions.map((version) => {
              const id = String(version.id ?? version.version_id);
              return (
                <option key={id} value={id}>
                  v{version.version} · {version.original_name || "未提供文件名"}
                </option>
              );
            })}
          </select>
        </label>
        {state.data?.version && (
          <span>
            当前查看：{state.data.version.name || "数据版本"} · v
            {state.data.version.version ?? "-"}
          </span>
        )}
      </div>
      {state.loading ? (
        <InlineLoading label="正在读取任务引用…" />
      ) : state.error ? (
        <div className="plan-state error dataset-reference-error" role="alert">
          <div>
            <b>任务引用读取失败</b>
            <p>{state.error}</p>
          </div>
          <Button icon={<ArrowClockwise size={16} />} onClick={() => load()}>
            重新加载
          </Button>
        </div>
      ) : !state.data?.items?.length ? (
        <EmptyState
          icon={Database}
          title="此版本尚未被任务引用"
          description="任务创建并固化该版本后会显示在这里。"
        />
      ) : (
        <>
          <div className="dataset-reference-list">
            {state.data.items.map((item) => (
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
                    <summary>固化版本快照</summary>
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
    </section>
  );
}

/** @param {{value?: Record<string, unknown>}} props */
function SnapshotFields({ value }) {
  const entries = Object.entries(value ?? {});
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

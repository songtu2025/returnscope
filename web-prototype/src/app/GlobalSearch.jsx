import { useEffect, useState } from "react";
import {
  CaretRight,
  Database,
  ListChecks,
  MagnifyingGlass,
  PlayCircle,
  Pulse,
} from "@phosphor-icons/react";
import { api } from "../api";
import { STATUS_LABELS } from "../constants";
import { useDialogFocus } from "../hooks/useDialogFocus";

/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */
/** @typedef {{id: string, title: string, owner_name: string, status: keyof typeof STATUS_LABELS, store: string, listing?: string}} SearchTask */
/** @typedef {{id: string, kind: string, name: string, current_version: number, row_count: number, description?: string}} SearchDataset */
/** @typedef {{id: string, workflow_status: string, comment: string, task_title: string, owner_name: string}} SearchReview */
/** @typedef {{tasks: SearchTask[], datasets: SearchDataset[], reviews: SearchReview[]}} SearchResources */
/** @typedef {{id: string, type: string, icon: import("react").ElementType, title: string, meta: string, keywords: string, page: string, focus: NavigationFocus}} GlobalSearchItem */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {{onClose: () => void, onSelect: Navigate, notify: Notify}} props */
export function GlobalSearch({ onClose, onSelect, notify }) {
  const [query, setQuery] = useState("");
  const [resources, setResources] = useState(
    /** @type {SearchResources} */ ({
      tasks: [],
      datasets: [],
      reviews: [],
    }),
  );
  const [loading, setLoading] = useState(false);
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  useEffect(() => {
    setLoading(true);
    Promise.all([api.tasks(), api.datasets(), api.reviews()])
      .then(([tasks, datasets, reviews]) => setResources({ tasks, datasets, reviews }))
      .catch((error) => notify(errorMessage(error), "error"))
      .finally(() => setLoading(false));
  }, [notify]);

  /** @type {GlobalSearchItem[]} */
  const items = [
    ...resources.tasks.map(
      /** @returns {GlobalSearchItem} */ (task) => ({
        id: task.id,
        type: "任务",
        icon: PlayCircle,
        title: task.title,
        meta: `${task.owner_name} · ${STATUS_LABELS[task.status] ?? task.status}`,
        keywords: `${task.title} ${task.store} ${task.listing ?? ""} ${task.owner_name}`,
        page: task.status === "completed" ? "legacy-results" : "analysis-tasks",
        focus: {
          kind: task.status === "completed" ? "result" : "task",
          id: task.id,
        },
      }),
    ),
    ...resources.datasets
      .filter((dataset) => dataset.kind === "products")
      .map(
        /** @returns {GlobalSearchItem} */ (dataset) => ({
          id: dataset.id,
          type: "产品信息",
          icon: Database,
          title: dataset.name,
          meta: `v${dataset.current_version} · ${dataset.row_count.toLocaleString()} 行`,
          keywords: `${dataset.name} ${dataset.description ?? ""} ${dataset.kind}`,
          page: "data-assets",
          focus: { kind: "dataset", id: dataset.id, datasetKind: dataset.kind },
        }),
      ),
    ...resources.reviews.map(
      /** @returns {GlobalSearchItem} */ (review) => ({
        id: review.id,
        type: review.workflow_status === "pending" ? "待复核" : "已复核",
        icon: ListChecks,
        title: review.comment,
        meta: `${review.task_title} · ${review.owner_name}`,
        keywords: `${review.comment} ${review.task_title} ${review.owner_name}`,
        page: "review",
        focus: { kind: "review", id: review.id, status: review.workflow_status },
      }),
    ),
  ];
  const normalized = query.trim().toLowerCase();
  const matches = items
    .filter(
      (item) =>
        !normalized ||
        `${item.title} ${item.keywords}`.toLowerCase().includes(normalized),
    )
    .slice(0, 12);

  return (
    <div
      className="command-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className="command-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="全局搜索"
        tabIndex={-1}
        onKeyDownCapture={constrainFocus}
      >
        <header>
          <MagnifyingGlass size={20} />
          <input
            aria-label="全局搜索"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && matches[0])
                onSelect(matches[0].page, matches[0].focus);
            }}
            placeholder="输入任务名、产品信息或评论…"
            data-dialog-initial-focus
          />
          <kbd>Esc</kbd>
        </header>
        <div className="command-results">
          {loading && (
            <div className="command-empty">
              <Pulse size={22} />
              正在读取工作区…
            </div>
          )}
          {!loading && matches.length === 0 && (
            <div className="command-empty">
              <MagnifyingGlass size={22} />
              没有找到匹配内容
            </div>
          )}
          {!loading &&
            matches.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={`${item.type}-${item.id}`}
                  onClick={() => onSelect(item.page, item.focus)}
                >
                  <span>
                    <Icon size={19} />
                  </span>
                  <div>
                    <b>{item.title}</b>
                    <small>{item.meta}</small>
                  </div>
                  <em>{item.type}</em>
                  <CaretRight size={16} />
                </button>
              );
            })}
        </div>
        <footer>
          <span>输入关键词筛选</span>
          <span>
            <kbd>Enter</kbd> 打开结果
          </span>
        </footer>
      </section>
    </div>
  );
}

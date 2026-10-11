import { useCallback, useEffect, useRef, useState } from "react";
import { CaretRight, MagnifyingGlass, Pulse } from "@phosphor-icons/react";
import { api } from "../api";
import { errorMessage } from "../shared/api/requestErrors";
import { matchingSearchItems } from "./globalSearchItems";
import { useDialogFocus } from "../hooks/useDialogFocus";

/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */
/** @typedef {import("./globalSearchItems").SearchResources} SearchResources */

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const resultsRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [tasks, datasets, reviews] = await Promise.all([
        api.tasks(),
        api.datasets(),
        api.reviews(),
      ]);
      setResources({ tasks, datasets, reviews });
    } catch (failure) {
      const message = errorMessage(failure);
      setError(message);
      notify(message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);
  useEffect(() => {
    load();
  }, [load]);

  const matches = matchingSearchItems(resources, query);

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
              if (!loading && !error && event.key === "Enter" && matches[0])
                onSelect(matches[0].page, matches[0].focus);
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const buttons = resultsRef.current?.querySelectorAll("button");
                const index =
                  event.key === "ArrowDown" ? 0 : (buttons?.length ?? 0) - 1;
                buttons?.[index]?.focus();
              }
            }}
            placeholder="输入任务名、产品信息或评论…"
            data-dialog-initial-focus
          />
          <kbd>Esc</kbd>
        </header>
        <div
          className="command-results"
          ref={resultsRef}
          onKeyDown={(event) => {
            if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
            event.preventDefault();
            const buttons = [...event.currentTarget.querySelectorAll("button")];
            const index = buttons.indexOf(
              /** @type {HTMLButtonElement} */ (event.target),
            );
            const next = buttons[index + (event.key === "ArrowDown" ? 1 : -1)];
            if (next) next.focus();
            else dialogRef.current?.querySelector("input")?.focus();
          }}
        >
          {loading && (
            <div className="command-empty">
              <Pulse size={22} />
              正在读取工作区…
            </div>
          )}
          {!loading && error && (
            <div className="command-empty" role="alert">
              <b>工作区读取失败</b>
              <span>{error}</span>
              <button className="secondary-button" onClick={load}>
                重新加载
              </button>
            </div>
          )}
          {!loading && !error && matches.length === 0 && (
            <div className="command-empty">
              <MagnifyingGlass size={22} />
              没有找到匹配内容
            </div>
          )}
          {!loading &&
            !error &&
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
            <kbd>↑↓</kbd> 选择 · <kbd>Enter</kbd> 打开结果
          </span>
        </footer>
      </section>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { CaretRight, MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../api";
import { errorMessage } from "../shared/api/requestErrors";
import { matchingSearchItems } from "./globalSearchItems";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { useLoadingHeight } from "../hooks/useLoadingHeight";
import { InlineLoading } from "../components/SharedUi";

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
      feedback: [],
    }),
  );
  const [loading, setLoading] = useState(true);
  const [hasData, setHasData] = useState(false);
  const [feedbackQuery, setFeedbackQuery] = useState("");
  const [loadError, setLoadError] = useState("");
  const [searchError, setSearchError] = useState("");
  const error = loadError || searchError;
  const [searching, setSearching] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const resultsRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const composing = useRef(false);
  useLoadingHeight(loading || searching, resultsRef);
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [tasks, datasets] = await Promise.all([
        api.tasks(),
        api.datasets("products"),
      ]);
      setResources((current) => ({ ...current, tasks, datasets }));
      setHasData(true);
    } catch (failure) {
      const message = errorMessage(failure);
      setLoadError(message);
      notify(message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const controller = new AbortController();
    if (!query.trim()) {
      setResources((current) => ({ ...current, feedback: [] }));
      setSearching(false);
      setSearchError("");
      return undefined;
    }
    setSearching(true);
    setSearchError("");
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.searchClassificationFeedback(query.trim(), {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setResources((current) => ({ ...current, feedback: result.items }));
          setFeedbackQuery(query.trim());
        }
      } catch (failure) {
        if (!controller.signal.aborted) setSearchError(errorMessage(failure));
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, attempt]);

  const matches = matchingSearchItems(
    {
      ...resources,
      feedback: feedbackQuery === query.trim() ? resources.feedback : [],
    },
    query,
  );

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
            onCompositionStart={() => {
              composing.current = true;
            }}
            onCompositionEnd={() => {
              composing.current = false;
            }}
            onKeyDown={(event) => {
              if (
                composing.current ||
                event.nativeEvent.isComposing ||
                event.keyCode === 229
              )
                return;
              if (!loading && !loadError && event.key === "Enter" && matches[0])
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
          <InlineLoading
            label="更新中…"
            compact
            active={hasData && (loading || searching)}
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
          {loading && !hasData && <InlineLoading label="正在读取工作区…" />}
          {!loading && !searching && error && (
            <div className="command-empty" role="alert">
              <b>{loadError ? "工作区读取失败" : "反馈搜索失败"}</b>
              <span>{error}</span>
              <button
                className="secondary-button"
                onClick={() => {
                  load();
                  setAttempt((value) => value + 1);
                }}
              >
                重新加载
              </button>
            </div>
          )}
          {!loading && !searching && !error && matches.length === 0 && (
            <div className="command-empty">
              <MagnifyingGlass size={22} />
              没有找到匹配内容
            </div>
          )}
          {hasData &&
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

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { CaretRight, MagnifyingGlass } from "@phosphor-icons/react";
import { api } from "../api";
import { errorMessage } from "../shared/api/requestErrors";
import { matchingSearchItems } from "./globalSearchItems";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { useLoadingHeight } from "../hooks/useLoadingHeight";
import { InlineLoading } from "../components/SharedUi";
import { serverStateKeys } from "../shared/serverState";

const searchResourceOptions = {
  shouldRetryOnError: false,
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
};

/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */
/** @typedef {import("./globalSearchItems").SearchResources} SearchResources */

/** @param {{onClose: () => void, onSelect: Navigate}} props */
export function GlobalSearch({ onClose, onSelect }) {
  const [query, setQuery] = useState("");
  const tasks = useSWR(
    ["analysis-tasks", "search"],
    () => api.tasks(),
    searchResourceOptions,
  );
  const products = useSWR(
    serverStateKeys.productDatasets,
    () => api.datasets("products"),
    searchResourceOptions,
  );
  const [feedback, setFeedback] = useState(
    /** @type {SearchResources["feedback"]} */ ([]),
  );
  const loading = tasks.isValidating || products.isValidating;
  const hasData = tasks.data !== undefined || products.data !== undefined;
  const [feedbackQuery, setFeedbackQuery] = useState("");
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const resultsRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const composing = useRef(false);
  useLoadingHeight(loading || searching, resultsRef);
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  useEffect(() => {
    const controller = new AbortController();
    if (!query.trim()) {
      setFeedback([]);
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
          setFeedback(result.items);
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
      tasks: tasks.data ?? [],
      datasets: products.data ?? [],
      feedback: feedbackQuery === query.trim() ? feedback : [],
    },
    query,
  );
  const failures = [
    {
      name: "任务",
      error: tasks.error ? errorMessage(tasks.error) : "",
      retry: () => tasks.mutate(),
      busy: tasks.isValidating,
    },
    {
      name: "产品信息",
      error: products.error ? errorMessage(products.error) : "",
      retry: () => products.mutate(),
      busy: products.isValidating,
    },
    {
      name: "反馈搜索",
      error: searchError,
      retry: () => setAttempt((value) => value + 1),
      busy: searching,
    },
  ].filter((item) => item.error);

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
              if (event.key === "Enter" && matches[0]) {
                event.preventDefault();
                onSelect(matches[0].page, matches[0].focus);
              }
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const buttons = [
                  ...(resultsRef.current?.querySelectorAll("button") ?? []),
                ].filter((button) => button.hasAttribute("data-search-result"));
                const index = event.key === "ArrowDown" ? 0 : buttons.length - 1;
                buttons[index]?.focus();
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
            if (
              !(event.target instanceof Element) ||
              !event.target.closest("[data-search-result]")
            )
              return;
            event.preventDefault();
            const buttons = [...event.currentTarget.querySelectorAll("button")].filter(
              (button) => button.hasAttribute("data-search-result"),
            );
            const index = buttons.indexOf(
              /** @type {HTMLButtonElement} */ (event.target),
            );
            const next = buttons[index + (event.key === "ArrowDown" ? 1 : -1)];
            if (next) next.focus();
            else dialogRef.current?.querySelector("input")?.focus();
          }}
        >
          {loading && !hasData && <InlineLoading label="正在读取工作区…" />}
          {failures.map((failure) => (
            <div className="command-error" role="alert" key={failure.name}>
              <div>
                <b>
                  {failure.name}
                  {failure.name === "反馈搜索" ? "失败" : "读取失败"}
                </b>
                <span>{failure.error}</span>
              </div>
              <button
                className="secondary-button compact-button"
                disabled={failure.busy}
                onClick={failure.retry}
              >
                重试{failure.name}
              </button>
            </div>
          ))}
          {!loading && !searching && !failures.length && matches.length === 0 && (
            <div className="command-empty">
              <MagnifyingGlass size={22} />
              没有找到匹配内容
            </div>
          )}
          {matches.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={`${item.type}-${item.id}`}
                data-search-result
                onClick={() => onSelect(item.page, item.focus)}
              >
                <span>
                  <Icon size={19} />
                </span>
                <div>
                  <b>{item.title}</b>
                  <small title={item.metaTitle || item.meta}>{item.meta}</small>
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

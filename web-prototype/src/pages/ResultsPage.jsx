import { useEffect, useMemo, useState } from "react";
import "../styles/analysis-workbench.css";

import { ChartBar, Plus } from "@phosphor-icons/react";
import { api } from "../api";
import { errorMessage } from "../shared/api/requestErrors";
import { AnalysisContext } from "../features/legacy-analysis/AnalysisContext";
import { AnalysisViews } from "../features/legacy-analysis/AnalysisViews";
import { AnalysisFilters } from "../features/legacy-analysis/AnalysisFilters";
import { EmptyState, InlineLoading, PageHeading } from "../components/SharedUi";

const EMPTY_FILTERS = {
  start_date: "",
  end_date: "",
  category_a: "",
  category_b: "",
  listing: "",
  sku: "",
  asin: "",
  reason: "",
  status: "",
  problem_code: "",
  claim_relation: "",
};

/** @typedef {import("../app/navigation").Navigate} Navigate */
/** @typedef {import("../features/legacy-analysis/AnalysisContext").AnalysisResultTask} AnalysisResultTask */
/** @typedef {import("../shared/api/legacyAnalysisContracts").LegacyAnalysis} LegacyAnalysis */
/** @typedef {import("../features/legacy-analysis/AnalysisContext").ResultsFocus} ResultsFocus */
/** @typedef {{notify: (message: string, tone?: string) => void, onNavigate: Navigate, focus?: ResultsFocus | null}} ResultsPageProps */

const resultsApi = {
  tasks: () => /** @type {Promise<AnalysisResultTask[]>} */ (api.tasks()),
  /** @param {string} id */
  task: (id) => /** @type {Promise<AnalysisResultTask>} */ (api.task(id)),
  /** @param {string} id @param {Record<string, string | number>} query @param {RequestInit} options */
  analysis: (id, query, options) =>
    /** @type {Promise<LegacyAnalysis>} */ (api.analysis(id, query, options)),
};

/** @param {ResultsPageProps} props */
export function ResultsPage({ notify, onNavigate, focus = null }) {
  const [tasks, setTasks] = useState(/** @type {AnalysisResultTask[]} */ ([]));
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [analysis, setAnalysis] = useState(/** @type {LegacyAnalysis | null} */ (null));
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [dimension, setDimension] = useState("listing");
  const [focusProblem, setFocusProblem] = useState("");
  const [page, setPage] = useState(1);
  const [activeTab, setActiveTab] = useState("overview");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const loadTasks = async () => {
      try {
        const values = await resultsApi.tasks();
        const completed = values.filter(
          (task) =>
            task.status === "completed" ||
            (task.status === "cancelled" && task.result_file_path),
        );
        if (focus?.id && !completed.some((task) => task.id === focus.id)) {
          const focusedTask = await resultsApi.task(focus.id);
          const listingReady = focusedTask.segments?.some(
            (segment) =>
              ["completed", "completed_with_errors"].includes(segment.status) &&
              segment.scope?.listing === focus.listing &&
              segment.result_file_path,
          );
          if (listingReady) completed.unshift(focusedTask);
        }
        if (!active) return;
        setTasks(completed);
        setSelectedId((current) =>
          focus?.id && completed.some((task) => task.id === focus.id)
            ? focus.id
            : completed.some((task) => task.id === current)
              ? current
              : (completed[0]?.id ?? null),
        );
        if (focus?.listing) {
          setFilters({ ...EMPTY_FILTERS, listing: focus.listing });
          setFiltersOpen(true);
        }
      } catch (error) {
        if (active) notify(errorMessage(error), "error");
      }
    };
    loadTasks();
    return () => {
      active = false;
    };
  }, [notify, focus?.id, focus?.listing]);

  const query = useMemo(
    () => ({
      ...filters,
      dimension,
      focus_problem: focusProblem,
      page,
      page_size: 50,
      view: activeTab,
    }),
    [filters, dimension, focusProblem, page, activeTab],
  );

  useEffect(() => {
    if (!selectedId) return undefined;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      resultsApi
        .analysis(selectedId, query, { signal: controller.signal })
        .then((value) => {
          if (active) setAnalysis(value);
        })
        .catch((error) => {
          if (active) notify(errorMessage(error), "error");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 150);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [selectedId, query, notify]);

  const task = tasks.find((item) => item.id === selectedId);
  const activeFilterCount = Object.values(filters).filter(Boolean).length;
  const downloadUrl = selectedId ? api.analysisDownloadUrl(selectedId, filters) : "#";

  /** @param {string} taskId */
  const changeTask = (taskId) => {
    setSelectedId(taskId);
    setFilters(EMPTY_FILTERS);
    setDimension("listing");
    setFocusProblem("");
    setPage(1);
    setActiveTab("overview");
  };

  /** @param {keyof typeof EMPTY_FILTERS} name @param {string} value */
  const changeFilter = (name, value) => {
    setFilters((current) => ({ ...current, [name]: value }));
    setFocusProblem("");
    setPage(1);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setFocusProblem("");
    setPage(1);
  };

  return (
    <div className="standard-page results-page analysis-workbench">
      <PageHeading
        eyebrow="可交付分析结果"
        title="退货问题分析"
        description="从全局问题发现到商品和评论证据下钻，所有指标均来自当前任务结果版本。"
      />

      {tasks.length === 0 && (
        <section className="empty-card">
          <EmptyState
            icon={ChartBar}
            title="还没有完成的分析"
            description="任务完成后，结果工作台和下载文件会出现在这里。"
            action={
              <button className="primary-button" onClick={() => onNavigate("new")}>
                <Plus size={17} />
                新建分析任务
              </button>
            }
          />
        </section>
      )}

      {task && (
        <>
          <AnalysisContext
            task={task}
            tasks={tasks}
            selectedId={selectedId}
            analysis={analysis}
            filters={filters}
            focus={focus}
            onChangeTask={changeTask}
            onNavigate={onNavigate}
            onQuality={() => setActiveTab("quality")}
            downloadUrl={downloadUrl}
          />

          {analysis && (
            <>
              <AnalysisFilters
                analysis={analysis}
                filters={filters}
                filtersOpen={filtersOpen}
                activeFilterCount={activeFilterCount}
                onReset={resetFilters}
                onToggle={() => setFiltersOpen((current) => !current)}
                onChange={changeFilter}
              />

              <AnalysisViews
                analysis={analysis}
                activeTab={activeTab}
                loading={loading}
                onTab={setActiveTab}
                onFocusProblem={(value) => {
                  setFocusProblem(value);
                  setPage(1);
                }}
                onDimension={(value) => {
                  setDimension(value);
                  setPage(1);
                }}
                onPage={setPage}
                downloadUrl={downloadUrl}
              />
            </>
          )}

          {!analysis && loading && (
            <div className="analysis-first-loading">
              <InlineLoading label="正在准备分析工作台…" />
            </div>
          )}
        </>
      )}
    </div>
  );
}

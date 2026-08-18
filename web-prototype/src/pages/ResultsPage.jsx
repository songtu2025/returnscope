import { useEffect, useMemo, useState } from "react";
import {
  ChartBar,
  CheckCircle,
  DownloadSimple,
  FunnelSimple,
  Plus,
  SlidersHorizontal,
  WarningCircle,
} from "@phosphor-icons/react";
import { api } from "../api";
import { EmptyState, PageHeading } from "../components/SharedUi";
import {
  DetailsSection,
  DiagnosisSection,
  OverviewSection,
  ProductsSection,
  QualitySection,
} from "../components/ResultsSections";
import { formatNumber, formatPercent, formatTime } from "../lib/presentation";

const TABS = [
  ["overview", "全站分析"],
  ["diagnosis", "问题诊断"],
  ["products", "商品下钻"],
  ["quality", "分类质量"],
  ["details", "数据明细"],
];

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

export function ResultsPage({ notify, onNavigate, focus = null }) {
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [analysis, setAnalysis] = useState(null);
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
        const values = await api.tasks();
        const completed = values.filter(
          (task) =>
            task.status === "completed" ||
            (task.status === "cancelled" && task.result_file_path),
        );
        if (focus?.id && !completed.some((task) => task.id === focus.id)) {
          const focusedTask = await api.task(focus.id);
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
        if (active) notify(error.message, "error");
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
      api
        .analysis(selectedId, query, { signal: controller.signal })
        .then((value) => {
          if (active) setAnalysis(value);
        })
        .catch((error) => {
          if (active) notify(error.message, "error");
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
  const isListingDelivery = task && !["completed", "cancelled"].includes(task.status);
  const activeFilterCount = Object.values(filters).filter(Boolean).length;
  const downloadUrl = selectedId ? api.analysisDownloadUrl(selectedId, filters) : "#";
  const activeViewReady = !analysis?.view || analysis.view === activeTab;
  const resultUnavailable = analysis?.quality_gate?.status === "unusable";
  const primaryQualityReason = analysis?.quality_gate?.review_reasons?.[0]?.name;
  const qualityAction = primaryQualityReason?.includes("品类")
    ? { page: "data", label: "补充商品信息" }
    : { page: "api", label: "检查模型配置" };

  const changeTask = (taskId) => {
    setSelectedId(taskId);
    setFilters(EMPTY_FILTERS);
    setDimension("listing");
    setFocusProblem("");
    setPage(1);
    setActiveTab("overview");
  };

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
          <section className="analysis-context-bar">
            <div className="analysis-task-picker">
              <label htmlFor="analysis-task">分析任务</label>
              <select
                id="analysis-task"
                value={selectedId ?? ""}
                onChange={(event) => changeTask(event.target.value)}
              >
                {tasks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                    {item.status === "cancelled" ? "（部分结果）" : ""}
                    {!["completed", "cancelled"].includes(item.status)
                      ? `（${focus?.listing ?? "已完成 Listing"} 阶段结果）`
                      : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="analysis-context-meta">
              <b>
                {task.store}
                {task.listing ? ` · ${task.listing}` : ""}
              </b>
              <span>
                {isListingDelivery
                  ? "Listing 结果"
                  : task.status === "cancelled"
                    ? "部分结果"
                    : "结果"}{" "}
                v{analysis?.task?.result_version ?? task.result_version} ·{" "}
                {task.dataset_name} v{task.dataset_version} ·{" "}
                {formatTime(analysis?.task?.completed_at ?? task.completed_at)}
              </span>
            </div>
            <a className="primary-button" href={downloadUrl}>
              <DownloadSimple size={18} />
              {isListingDelivery
                ? `下载 ${filters.listing} 结果`
                : task.status === "cancelled"
                  ? "下载部分结果"
                  : "下载当前结果"}
            </a>
          </section>

          {isListingDelivery && analysis && !resultUnavailable && (
            <div className="plan-state success" role="status">
              <CheckCircle size={19} />
              <div>
                <b>{filters.listing} 已完成，可以先查看和下载</b>
                <p>
                  本页只统计该 Listing 的已交付结果；批量任务中的其他 Listing
                  继续独立运行。
                </p>
              </div>
            </div>
          )}

          {analysis && resultUnavailable && (
            <div className="plan-state warning result-quality-warning" role="alert">
              <WarningCircle size={19} />
              <div>
                <b>本批结果尚不能用于问题分析</b>
                <p>
                  {formatNumber(analysis.quality_gate.text_records)} 条有效评论中，
                  {formatNumber(analysis.quality_gate.labeled_records)} 条形成问题标签；
                  {formatNumber(analysis.quality_gate.review_records)} 条进入人工复核。
                  当前没有可聚合的问题标签，因此图表为空。
                  {primaryQualityReason && ` 最常见复核原因：${primaryQualityReason}。`}
                </p>
              </div>
              <div className="result-quality-actions">
                <button
                  className="secondary-button"
                  onClick={() => setActiveTab("quality")}
                >
                  查看复核原因
                </button>
                <button
                  className="primary-button"
                  onClick={() => onNavigate(qualityAction.page)}
                >
                  {qualityAction.label}
                </button>
              </div>
            </div>
          )}

          {task.status === "cancelled" && (
            <div className="plan-state warning" role="status">
              <WarningCircle size={19} />
              <div>
                <b>当前为部分结果</b>
                <p>仅包含取消前已经完成的 Listing 片段；未完成片段未计入本页指标。</p>
              </div>
            </div>
          )}

          {analysis && (
            <>
              <section
                className={`analysis-filter-panel ${filtersOpen ? "is-open" : ""}`}
              >
                <header>
                  <div>
                    <FunnelSimple size={19} />
                    <div>
                      <b>分析筛选</b>
                      <span>
                        当前范围 {formatNumber(analysis.scope.filtered_records)} /{" "}
                        {formatNumber(analysis.scope.total_records)} 条退货记录
                      </span>
                    </div>
                  </div>
                  <div>
                    {activeFilterCount > 0 && (
                      <button className="text-button" onClick={resetFilters}>
                        重置筛选
                      </button>
                    )}
                    <button
                      className="secondary-button"
                      onClick={() => setFiltersOpen((current) => !current)}
                      aria-expanded={filtersOpen}
                    >
                      <SlidersHorizontal size={17} />
                      {filtersOpen
                        ? "收起"
                        : `展开${activeFilterCount ? `（${activeFilterCount}）` : ""}`}
                    </button>
                  </div>
                </header>
                {filtersOpen && (
                  <div className="analysis-filter-grid">
                    <FilterInput
                      label="开始日期"
                      type="date"
                      min={analysis.filters.date_min ?? undefined}
                      max={analysis.filters.date_max ?? undefined}
                      value={filters.start_date}
                      onChange={(value) => changeFilter("start_date", value)}
                    />
                    <FilterInput
                      label="结束日期"
                      type="date"
                      min={analysis.filters.date_min ?? undefined}
                      max={analysis.filters.date_max ?? undefined}
                      value={filters.end_date}
                      onChange={(value) => changeFilter("end_date", value)}
                    />
                    <FilterSelect
                      label="Listing"
                      value={filters.listing}
                      options={analysis.filters.listings}
                      onChange={(value) => changeFilter("listing", value)}
                    />
                    <FilterSelect
                      label="问题标签"
                      value={filters.problem_code}
                      options={analysis.filters.problem_labels}
                      optionValue="code"
                      optionLabel="name"
                      onChange={(value) => changeFilter("problem_code", value)}
                    />
                    <FilterSelect
                      label="处理状态"
                      value={filters.status}
                      options={analysis.filters.statuses}
                      onChange={(value) => changeFilter("status", value)}
                    />
                    <FilterSelect
                      label="品类A"
                      value={filters.category_a}
                      options={analysis.filters.category_as}
                      onChange={(value) => changeFilter("category_a", value)}
                    />
                    <FilterSelect
                      label="品类B"
                      value={filters.category_b}
                      options={analysis.filters.category_bs}
                      onChange={(value) => changeFilter("category_b", value)}
                    />
                    <FilterSelect
                      label="Amazon 原因"
                      value={filters.reason}
                      options={analysis.filters.reasons}
                      onChange={(value) => changeFilter("reason", value)}
                    />
                    <FilterSelect
                      label="SKU"
                      value={filters.sku}
                      options={analysis.filters.skus}
                      onChange={(value) => changeFilter("sku", value)}
                    />
                    <FilterSelect
                      label="Listing 承诺关系"
                      value={filters.claim_relation}
                      options={analysis.filters.claim_relations}
                      onChange={(value) => changeFilter("claim_relation", value)}
                    />
                  </div>
                )}
              </section>

              <MetricCards metrics={analysis.overview.metrics} />

              <div className="analysis-tabs" role="tablist" aria-label="分析结果视图">
                {TABS.map(([id, label]) => (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={activeTab === id}
                    className={activeTab === id ? "active" : ""}
                    onClick={() => setActiveTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className={`analysis-tab-panel ${loading ? "is-loading" : ""}`}>
                {activeViewReady && activeTab === "overview" && (
                  <OverviewSection
                    overview={analysis.overview}
                    qualityGate={analysis.quality_gate}
                  />
                )}
                {activeViewReady && activeTab === "diagnosis" && (
                  <DiagnosisSection
                    diagnosis={analysis.diagnosis}
                    onFocusProblem={(value) => {
                      setFocusProblem(value);
                      setPage(1);
                    }}
                  />
                )}
                {activeViewReady && activeTab === "products" && (
                  <ProductsSection
                    products={analysis.products}
                    onDimension={(value) => {
                      setDimension(value);
                      setPage(1);
                    }}
                  />
                )}
                {activeViewReady && activeTab === "quality" && (
                  <QualitySection quality={analysis.quality} />
                )}
                {activeViewReady && activeTab === "details" && (
                  <DetailsSection
                    details={analysis.details}
                    onPage={setPage}
                    downloadUrl={downloadUrl}
                  />
                )}
                {loading && <div className="analysis-loading">正在更新分析结果…</div>}
              </div>
            </>
          )}

          {!analysis && loading && (
            <div className="analysis-first-loading">正在准备分析工作台…</div>
          )}
        </>
      )}
    </div>
  );
}

function FilterInput({ label, value, onChange, ...props }) {
  return (
    <label className="analysis-filter-field">
      <span>{label}</span>
      <input
        {...props}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function FilterSelect({
  label,
  value,
  options = [],
  optionValue = null,
  optionLabel = null,
  onChange,
}) {
  return (
    <label className="analysis-filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">全部</option>
        {options.map((option) => {
          const optionId = optionValue ? option[optionValue] : option;
          const optionName = optionLabel ? option[optionLabel] : option;
          return (
            <option key={optionId} value={optionId}>
              {optionName}
            </option>
          );
        })}
      </select>
    </label>
  );
}

function MetricCards({ metrics }) {
  const cards = [
    ["退货记录", formatNumber(metrics.total_records), "当前筛选范围"],
    [
      "覆盖 Listing",
      formatNumber(metrics.listing_count),
      `${formatNumber(metrics.sku_count)} 个 SKU`,
    ],
    [
      "有效评论",
      formatNumber(metrics.text_records),
      `文本覆盖率 ${formatPercent(metrics.text_coverage)}`,
    ],
    [
      "需人工复核",
      formatNumber(metrics.review_records),
      `占有效评论 ${formatPercent(metrics.review_rate)}`,
    ],
    [
      "产品信息匹配",
      formatNumber(metrics.product_matched),
      `匹配率 ${formatPercent(metrics.product_match_rate)}`,
    ],
  ];
  return (
    <div className="analysis-kpis">
      {cards.map(([label, value, note]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{note}</small>
        </div>
      ))}
    </div>
  );
}

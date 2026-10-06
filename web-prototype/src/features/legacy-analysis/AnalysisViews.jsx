import { InlineLoading } from "../../components/SharedUi";
import { formatNumber, formatPercent } from "../../lib/presentation";
import { OverviewSection } from "./OverviewSection";
import { DiagnosisSection } from "./DiagnosisSection";
import { ProductsSection } from "./ProductsSection";
import { QualitySection } from "./QualitySection";
import { DetailsSection } from "./DetailsSection";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").LegacyAnalysis} LegacyAnalysis */
/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisMetrics} AnalysisMetrics */
/** @typedef {{analysis: LegacyAnalysis, activeTab: string, loading: boolean, onTab: (tab: string) => void, onFocusProblem: (code: string) => void, onDimension: (dimension: string) => void, onPage: (page: number) => void, downloadUrl: string}} AnalysisViewsProps */

const TABS = [
  ["overview", "全站分析"],
  ["diagnosis", "问题诊断"],
  ["products", "商品下钻"],
  ["quality", "分类质量"],
  ["details", "数据明细"],
];

/** @param {{metrics: AnalysisMetrics}} props */
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

/** @param {Pick<AnalysisViewsProps, "activeTab" | "onTab">} props */
function AnalysisTabs({ activeTab, onTab }) {
  return (
    <div className="analysis-tabs" role="tablist" aria-label="分析结果视图">
      {TABS.map(([id, label]) => (
        <button
          key={id}
          role="tab"
          aria-selected={activeTab === id}
          className={activeTab === id ? "active" : ""}
          onClick={() => onTab(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** @param {AnalysisViewsProps} props */
function AnalysisSection({
  analysis,
  activeTab,
  onFocusProblem,
  onDimension,
  onPage,
  downloadUrl,
}) {
  if (activeTab === "overview") {
    return (
      <OverviewSection
        overview={analysis.overview}
        qualityGate={analysis.quality_gate}
      />
    );
  }
  if (activeTab === "diagnosis") {
    return (
      <DiagnosisSection
        diagnosis={analysis.diagnosis}
        onFocusProblem={onFocusProblem}
      />
    );
  }
  if (activeTab === "products") {
    return <ProductsSection products={analysis.products} onDimension={onDimension} />;
  }
  if (activeTab === "quality") return <QualitySection quality={analysis.quality} />;
  if (activeTab === "details") {
    return (
      <DetailsSection
        details={analysis.details}
        onPage={onPage}
        downloadUrl={downloadUrl}
      />
    );
  }
  return null;
}

/** @param {AnalysisViewsProps} props */
export function AnalysisViews(props) {
  const { analysis, activeTab, loading, onTab } = props;
  const activeViewReady = !analysis?.view || analysis.view === activeTab;
  return (
    <>
      <MetricCards metrics={analysis.overview.metrics} />
      <AnalysisTabs activeTab={activeTab} onTab={onTab} />
      <div className={`analysis-tab-panel ${loading ? "is-loading" : ""}`}>
        {activeViewReady && <AnalysisSection {...props} />}
        {loading && (
          <div className="analysis-loading">
            <InlineLoading label="正在更新分析结果…" />
          </div>
        )}
      </div>
    </>
  );
}

import { formatNumber, formatPercent } from "../../lib/presentation";
import { SectionCard, EmptyAnalysis } from "./LegacyAnalysisDisplay";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisProducts} AnalysisProducts */

/** @type {Record<string, string>} */
const dimensionLabels = {
  listing: "Listing",
  category_b: "品类B",
  sku: "SKU",
  asin: "ASIN",
};

/** @param {{products: AnalysisProducts, onDimension: (dimension: string) => void}} props */
function ProductDimension({ products, onDimension }) {
  return (
    <div className="dimension-switch" role="group" aria-label="商品分析维度">
      {Object.entries(dimensionLabels).map(([value, label]) => (
        <button
          key={value}
          className={products.dimension === value ? "active" : ""}
          onClick={() => onDimension(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** @param {{row: NonNullable<AnalysisProducts["matrix"]>[number], maximum: number}} props */
function HeatmapRow({ row, maximum }) {
  return (
    <tr key={row.name}>
      <td className="is-strong">{row.name}</td>
      {row.values.map((item) => (
        <td
          key={item.label}
          style={{
            backgroundColor: `rgba(22, 118, 93, ${0.08 + (item.records / maximum) * 0.72})`,
          }}
        >
          {formatNumber(item.records)}
        </td>
      ))}
    </tr>
  );
}

/** @param {{products: AnalysisProducts}} props */
function ProductHeatmap({ products }) {
  const matrix = products.matrix ?? [];
  const labels = matrix[0]?.values?.map((item) => item.label) ?? [];
  const maximum = Math.max(
    ...matrix.flatMap((row) => row.values.map((item) => item.records)),
    1,
  );
  return (
    <SectionCard title="商品与主因分布" note="颜色越深表示该商品的问题记录越集中">
      {matrix.length ? (
        <div className="analysis-table-scroll heatmap-scroll">
          <table className="analysis-table heatmap-table">
            <thead>
              <tr>
                <th>{dimensionLabels[products.dimension]}</th>
                {labels.map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.map((row) => (
                <HeatmapRow key={row.name} row={row} maximum={maximum} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyAnalysis />
      )}
    </SectionCard>
  );
}

/** @param {{products: AnalysisProducts}} props */
function ProductSummary({ products }) {
  return (
    <SectionCard title="商品统计" note="同时比较规模、评论覆盖和复核压力">
      {products.summary?.length ? (
        <div className="analysis-table-scroll">
          <table className="analysis-table">
            <thead>
              <tr>
                <th>{dimensionLabels[products.dimension]}</th>
                <th>退货记录</th>
                <th>评论覆盖</th>
                <th>需复核</th>
                <th>复核占比</th>
                <th>首要问题</th>
              </tr>
            </thead>
            <tbody>
              {products.summary.map((row) => (
                <tr key={row.name}>
                  <td className="is-strong">{row.name}</td>
                  <td>{formatNumber(row.records)}</td>
                  <td>{formatPercent(row.text_coverage)}</td>
                  <td>{formatNumber(row.review_records)}</td>
                  <td>{formatPercent(row.review_rate)}</td>
                  <td>{row.top_problem || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyAnalysis />
      )}
    </SectionCard>
  );
}

/** @param {{products: AnalysisProducts, onDimension: (dimension: string) => void}} props */
export function ProductsSection({ products, onDimension }) {
  return (
    <div className="analysis-section-stack">
      <ProductDimension products={products} onDimension={onDimension} />

      <ProductHeatmap products={products} />

      <ProductSummary products={products} />
    </div>
  );
}

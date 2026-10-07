import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  formatDate,
  formatPercent,
  shortDate,
} from "./returnReasonInsightPresentation";
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightProduct} InsightProduct */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{data: DashboardInsights, selected: InsightReason, terms: AnalysisContextTerms}} props */
function ReasonTrendPlot({ data, selected, terms }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart
        data={data.trend}
        margin={{ top: 14, right: 8, bottom: 4, left: 8 }}
      >
        <CartesianGrid stroke="#e7ece9" vertical={false} />
        <XAxis
          dataKey="period_start"
          tickFormatter={shortDate}
          tick={{ fill: "#738079", fontSize: 10 }}
          tickLine={false}
          axisLine={{ stroke: "#dce2dd" }}
          minTickGap={22}
        />
        <YAxis
          yAxisId="rate"
          tickFormatter={(value) => `${value}%`}
          tick={{ fill: "#738079", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <YAxis yAxisId="volume" orientation="right" hide />
        <Tooltip
          labelFormatter={(value) => `周起始 ${formatDate(value)}`}
          formatter={(value, name, item) =>
            name === terms.weeklyVolumeLabel
              ? [`${value} 条`, name]
              : [
                  `${Number(value).toFixed(1)}%（${item.payload.record_count} 条）`,
                  `${selected.label}占比`,
                ]
          }
        />
        <Bar
          yAxisId="volume"
          name={terms.weeklyVolumeLabel}
          dataKey="total_record_count"
          fill="#dcebe5"
          radius={[3, 3, 0, 0]}
          maxBarSize={18}
        />
        <Line
          yAxisId="rate"
          type="monotone"
          dataKey="percentage"
          stroke="#12765b"
          strokeWidth={2.4}
          dot={{ r: 2.8, fill: "#fff", strokeWidth: 2 }}
          activeDot={{ r: 4.5 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** @param {{data: DashboardInsights, selected: InsightReason, terms: AnalysisContextTerms}} props */
function ReasonTrend({ data, selected, terms }) {
  return (
    <section className="return-insight-card return-insight-trend">
      <header>
        <div>
          <h3>{selected.label}原因占比趋势</h3>
          <span>柱形为{terms.weeklyVolumeLabel}，折线为原因占比</span>
        </div>
        <b>按周</b>
      </header>
      {data.trend?.length ? (
        <div className="return-insight-chart">
          <ReasonTrendPlot data={data} selected={selected} terms={terms} />
        </div>
      ) : (
        <div className="return-insight-empty">当前范围没有可用日期</div>
      )}
      <footer>
        <i /> {selected.label}占比
        <span>样本少于 10 条的周仅作观察</span>
      </footer>
    </section>
  );
}

/** @param {{product: InsightProduct, index: number, selected: InsightReason, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function ProductHotspot({ product, index, selected, onUpdateRoute }) {
  return (
    <button
      onClick={() =>
        onUpdateRoute({
          productName: product.value,
          productSku: "",
          problem: selected.value,
          recordPage: 1,
        })
      }
    >
      <span>{index + 1}</span>
      <div>
        <b title={product.value}>{product.value}</b>
        <small>
          {product.record_count} 条相关 / 样本 {product.total_record_count}
        </small>
        <i aria-hidden="true">
          <span
            style={{
              width: `${Math.min(product.product_reason_rate, 100)}%`,
            }}
          />
        </i>
      </div>
      <strong>{formatPercent(product.product_reason_rate)}</strong>
      <em className={product.lift > 1 ? "high" : ""}>
        {Number(product.lift || 0).toFixed(2)}×
      </em>
    </button>
  );
}

/** @param {{products: InsightProduct[], selected: InsightReason, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function ProductHotspots({ products, selected, onUpdateRoute }) {
  return (
    <section className="return-insight-card return-product-hotspot">
      <header>
        <div>
          <h3>商品热点</h3>
          <span>对比商品内部发生率与整体基线</span>
        </div>
        <b>基线 {formatPercent(selected.percentage)}</b>
      </header>
      {products.length ? (
        <div className="return-product-hotspot-list">
          {products.slice(0, 3).map((product, index) => (
            <ProductHotspot
              key={product.value}
              product={product}
              index={index}
              selected={selected}
              onUpdateRoute={onUpdateRoute}
            />
          ))}
        </div>
      ) : (
        <div className="return-insight-empty">当前范围没有匹配产品</div>
      )}
      <footer>仅将样本量 ≥15 的商品作为稳定比较依据</footer>
    </section>
  );
}

/** @param {{data: DashboardInsights, selected: InsightReason, products: InsightProduct[], terms: AnalysisContextTerms, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonDiagnosticOverview({
  data,
  selected,
  products,
  terms,
  onUpdateRoute,
}) {
  return (
    <div className="return-diagnostic-overview">
      <ReasonTrend data={data} selected={selected} terms={terms} />
      <ProductHotspots
        products={products}
        selected={selected}
        onUpdateRoute={onUpdateRoute}
      />
    </div>
  );
}

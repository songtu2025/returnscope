import { useState } from "react";
import { Info, Quotes } from "@phosphor-icons/react";
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
  partLabel,
  selectedSemanticUnit,
  shortDate,
} from "./returnReasonInsightPresentation";
import { analysisContextTerms } from "./analysisContextPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightEvidence} InsightEvidence */
/** @typedef {import("./analysisDashboardContracts").InsightProduct} InsightProduct */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {import("./analysisDashboardContracts").InsightSemanticProfile} InsightSemanticProfile */
/** @typedef {{data: DashboardInsights, selected?: InsightReason, products: InsightProduct[], coReasons: InsightReason[], semanticProfile: InsightSemanticProfile, evidence: InsightEvidence, analysisContext: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} ReturnReasonInsightDiagnosticProps */

/** @param {ReturnReasonInsightDiagnosticProps} props */
export function ReturnReasonInsightDiagnostic({
  data,
  selected,
  products,
  coReasons,
  semanticProfile,
  evidence,
  analysisContext,
  onUpdateRoute,
  onEvidence,
}) {
  const [showDefinition, setShowDefinition] = useState(false);
  const terms = analysisContextTerms(analysisContext);

  return (
    <main className="return-insight-diagnostic">
      {selected ? (
        <>
          <header className="return-diagnostic-header">
            <div className="return-diagnostic-title">
              <span>2</span>
              <div>
                <p>原因诊断</p>
                <h2>{selected.label}</h2>
              </div>
            </div>
            <div className="return-diagnostic-metrics">
              <InsightStat label="相关评论" value={`${selected.record_count} 条`} />
              <InsightStat
                label={terms.shareLabel}
                value={formatPercent(selected.percentage)}
              />
              <InsightStat
                label="核心原因率"
                value={formatPercent(selected.primary_rate)}
              />
            </div>
            <button
              className={showDefinition ? "active" : ""}
              aria-expanded={showDefinition}
              onClick={() => setShowDefinition((visible) => !visible)}
            >
              <Info size={16} /> 查看定义
            </button>
          </header>

          {showDefinition && (
            <div className="return-diagnostic-definition">
              <b>{selected.label}</b>
              <span>
                统计包含该问题标签的去重评论；核心原因率表示该标签进入评论的
                primary_label_codes，不等同于唯一责任归因。
              </span>
            </div>
          )}

          <div className="return-diagnostic-overview">
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
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={data.trend}
                      margin={{ top: 14, right: 8, bottom: 4, left: 0 }}
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
                        width={34}
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
                </div>
              ) : (
                <div className="return-insight-empty">当前范围没有可用日期</div>
              )}
              <footer>
                <i /> {selected.label}占比
                <span>样本少于 10 条的周仅作观察</span>
              </footer>
            </section>

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
                    <button
                      key={product.value}
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
                          {product.record_count} 条相关 / 样本{" "}
                          {product.total_record_count}
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
                  ))}
                </div>
              ) : (
                <div className="return-insight-empty">当前范围没有匹配产品</div>
              )}
              <footer>仅将样本量 ≥15 的商品作为稳定比较依据</footer>
            </section>
          </div>

          <section className="return-semantic-profile">
            <header>
              <div>
                <Quotes size={18} />
                <div>
                  <h3>语义特征</h3>
                  <span>
                    {semanticProfile.record_count || 0} 条评论具有对应语义证据 · 覆盖
                    {formatPercent(semanticProfile.coverage)}
                  </span>
                </div>
              </div>
            </header>
            <div>
              <SemanticGroup
                label="问题部位"
                items={(semanticProfile.parts ?? []).slice(0, 3).map((item) => ({
                  key: item.value,
                  text: `${partLabel(item.value)} ${item.record_count}`,
                }))}
              />
              <SemanticGroup
                label="伴随原因"
                items={coReasons.slice(0, 3).map((item) => ({
                  key: item.value,
                  text: `${item.label} ${item.record_count} · ${Number(
                    item.lift || 0,
                  ).toFixed(2)}×`,
                  onClick: () => onUpdateRoute({ problem: item.value, recordPage: 1 }),
                }))}
              />
              <SemanticGroup
                label="高频表述"
                items={(semanticProfile.opinions ?? []).slice(0, 2).map((item) => ({
                  key: `${item.opinion}-${item.part}`,
                  text: `${item.opinion} ${item.record_count}`,
                }))}
              />
            </div>
          </section>

          <section className="return-insight-card return-insight-evidence">
            <header>
              <div>
                <h3>语义证据</h3>
                <span>原始评论与结构化语义单元一一对应</span>
              </div>
              <b>共 {Number(evidence.total || 0).toLocaleString()} 条</b>
            </header>
            {evidence.items?.length ? (
              <div className="return-insight-evidence-table">
                <div className="return-insight-evidence-head">
                  <span>原始评论</span>
                  <span>中文意见</span>
                  <span>产品 / SKU</span>
                  <span>部位</span>
                  <span />
                </div>
                {evidence.items.map((record) => {
                  const unit = selectedSemanticUnit(record, selected.value);
                  return (
                    <article key={record.id || record.source_record_id}>
                      <p title={record.comment || record.reason || undefined}>
                        {record.comment || record.reason || terms.missingText}
                      </p>
                      <div>
                        <b>{unit.opinion || selected.label}</b>
                        <small>{formatDate(record.return_date)}</small>
                      </div>
                      <div>
                        <b>{record.product_name || "未提供产品"}</b>
                        <small>
                          {record.product_sku || record.source_sku || "未提供 SKU"}
                        </small>
                      </div>
                      <span className="return-part-pill">{partLabel(unit.part)}</span>
                      <button
                        className="text-button"
                        onClick={(event) => onEvidence(record, event.currentTarget)}
                      >
                        查看证据
                      </button>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="return-insight-empty">当前原因没有可展示的评论证据</div>
            )}
          </section>
        </>
      ) : (
        <div className="return-insight-empty return-diagnostic-empty">
          {terms.selectReasonPrompt}
        </div>
      )}
    </main>
  );
}

/** @param {{label: string, value: string}} props */
function InsightStat({ label, value }) {
  return (
    <div className="return-insight-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

/** @param {{label: string, items: Array<{key: string, text: string, onClick?: () => void}>}} props */
function SemanticGroup({ label, items }) {
  return (
    <div className="return-semantic-group">
      <b>{label}</b>
      <div>
        {items.length ? (
          items.map((item) =>
            item.onClick ? (
              <button key={item.key} onClick={item.onClick}>
                {item.text}
              </button>
            ) : (
              <span key={item.key}>{item.text}</span>
            ),
          )
        ) : (
          <span>暂无稳定特征</span>
        )}
      </div>
    </div>
  );
}

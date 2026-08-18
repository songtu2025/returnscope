import { useState } from "react";
import {
  ArrowCounterClockwise,
  CalendarBlank,
  Info,
  Quotes,
  ShieldCheck,
  TrendUp,
  WarningCircle,
} from "@phosphor-icons/react";
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

const GROUP_ORDER = ["尺码与合脚", "外观", "体感", "功能", "其他原因"];
const PART_LABELS = {
  WHOLE_SHOE: "整鞋",
  TOE: "鞋头",
  OPENING: "鞋口",
  OUTSOLE: "外底",
  INSOLE: "鞋垫",
  UPPER: "鞋面",
  HEEL: "后跟",
  UNSPECIFIED: "未明确部位",
};

function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function formatDate(value) {
  if (!value) return "未提供";
  return String(value).slice(0, 10);
}

function shortDate(value) {
  const text = formatDate(value);
  return text === "未提供" ? text : text.slice(5).replace("-", "/");
}

function filterOptions(values) {
  return Array.isArray(values) ? values : [];
}

function partLabel(value) {
  return PART_LABELS[value] || String(value || "未明确部位").replaceAll("_", " ");
}

function selectedSemanticUnit(record, labelCode) {
  const units = record.classification?.semantic_units ?? [];
  return units.find((unit) => unit.label_code === labelCode) ?? units[0] ?? {};
}

export function ReturnReasonInsights({
  route,
  updateRoute,
  data,
  loading,
  onEvidence,
}) {
  const [selectedSubject, setSelectedSubject] = useState("");
  const [showDefinition, setShowDefinition] = useState(false);
  const summary = data.summary ?? {};
  const reasons = data.reasons ?? [];
  const selected = data.selected_reason;
  const products = data.products ?? [];
  const coReasons = data.co_reasons ?? [];
  const semanticProfile = data.semantic_profile ?? {};
  const evidence = data.evidence ?? { items: [], total: 0 };
  const options = data.filter_options ?? {};
  const dateRange = data.date_range ?? {};
  const subjects = data.subject_breakdown ?? [];
  const groups = GROUP_ORDER.filter((item) =>
    (data.category_groups ?? []).includes(item),
  );
  const visibleReasons = selectedSubject
    ? reasons.filter((reason) => reason.subjects?.includes(selectedSubject))
    : reasons;
  const topReasonCount = Math.max(
    ...visibleReasons.map((item) => item.record_count),
    1,
  );
  const includedCount = Number(summary.record_count || data.total_record_count || 0);
  const totalCount = Number(summary.total_record_count ?? includedCount);
  const pendingCount = Number(summary.pending_review_record_count || 0);

  const updateFilters = (changes) =>
    updateRoute({
      ...changes,
      problem: changes.problem ?? route.problem,
      recordPage: 1,
    });

  const chooseSubject = (subject) => {
    setSelectedSubject(subject);
    const firstReason = subject
      ? reasons.find((reason) => reason.subjects?.includes(subject))
      : reasons[0];
    updateRoute({
      problem:
        selected && (!subject || selected.subjects?.includes(subject))
          ? selected.value
          : firstReason?.value || "",
      recordPage: 1,
    });
  };

  const resetReasonFilters = () => {
    setSelectedSubject("");
    updateRoute({ labelGroup: "", problem: "", recordPage: 1 });
  };

  return (
    <div className={`return-insight-content ${loading ? "is-loading" : ""}`}>
      <section className="return-insight-filters" aria-label="退货原因洞察筛选">
        <label className="return-insight-date-filter">
          <span>时间</span>
          <div>
            <CalendarBlank size={17} />
            <input
              aria-label="开始日期"
              type="date"
              value={route.dateFrom || dateRange.date_from || ""}
              min={dateRange.date_from || undefined}
              max={route.dateTo || dateRange.date_to || undefined}
              onChange={(event) =>
                updateFilters({ dateFrom: event.target.value, problem: "" })
              }
            />
            <i>至</i>
            <input
              aria-label="结束日期"
              type="date"
              value={route.dateTo || dateRange.date_to || ""}
              min={route.dateFrom || dateRange.date_from || undefined}
              max={dateRange.date_to || undefined}
              onChange={(event) =>
                updateFilters({ dateTo: event.target.value, problem: "" })
              }
            />
          </div>
        </label>
        <InsightSelect
          label="Listing"
          value={route.listing}
          values={options.listings}
          allLabel="全部 Listing"
          onChange={(listing) =>
            updateFilters({
              listing,
              productName: "",
              productSku: "",
              problem: "",
            })
          }
        />
        <InsightSelect
          label="产品"
          value={route.productName}
          values={options.product_names}
          allLabel="全部产品"
          onChange={(productName) =>
            updateFilters({ productName, productSku: "", problem: "" })
          }
        />
        <InsightSelect
          label="SKU"
          value={route.productSku}
          values={options.product_skus}
          allLabel="全部 SKU"
          onChange={(productSku) => updateFilters({ productSku, problem: "" })}
        />
      </section>

      <section className="return-insight-trust" aria-label="数据可信度">
        <div>
          <ShieldCheck size={19} weight="duotone" />
          <span>有效样本</span>
          <b>{Number(data.total_record_count || 0).toLocaleString()} 条</b>
        </div>
        <div>
          <TrendUp size={18} />
          <span>问题标签覆盖</span>
          <b>{formatPercent(data.label_coverage)}</b>
        </div>
        <div className={pendingCount ? "warning" : ""}>
          <WarningCircle size={18} />
          <span>待复核</span>
          <b>{pendingCount.toLocaleString()} 条</b>
        </div>
        <p>
          当前洞察使用已确认与自动通过的数据；多标签原因占比之和可能超过 100%。
          <span>
            已分析 {includedCount.toLocaleString()}/{totalCount.toLocaleString()} 条
          </span>
        </p>
      </section>

      <div className="return-insight-workbench">
        <aside className="return-insight-explorer" aria-label="选择主题与退货原因">
          <header>
            <div>
              <span>1</span>
              <div>
                <h2>选择主题与原因</h2>
                <p>先定位问题对象，再进入具体原因</p>
              </div>
            </div>
            <button onClick={resetReasonFilters}>
              <ArrowCounterClockwise size={15} /> 重置
            </button>
          </header>

          <section className="return-subject-list">
            <h3>问题对象</h3>
            {subjects.map((subject) => (
              <button
                key={subject.value}
                className={selectedSubject === subject.value ? "active" : ""}
                onClick={() =>
                  chooseSubject(selectedSubject === subject.value ? "" : subject.value)
                }
              >
                <div>
                  <b>{subject.label}</b>
                  <span>{subject.record_count} 条记录</span>
                </div>
                <i aria-hidden="true">
                  <span style={{ width: `${Math.min(subject.percentage, 100)}%` }} />
                </i>
                <strong>{formatPercent(subject.percentage)}</strong>
              </button>
            ))}
          </section>

          <section className="return-reason-groups">
            <h3>原因类别</h3>
            <nav aria-label="退货原因类别">
              {["", ...groups].map((group) => (
                <button
                  key={group || "all"}
                  className={route.labelGroup === group ? "active" : ""}
                  onClick={() =>
                    updateRoute({ labelGroup: group, problem: "", recordPage: 1 })
                  }
                >
                  {group || "全部"}
                </button>
              ))}
            </nav>
          </section>

          <section className="return-reason-ranking">
            <header>
              <div>
                <h3>具体退货原因</h3>
                <p>按有效退货记录排序</p>
              </div>
              <span>{visibleReasons.length} 项</span>
            </header>
            {visibleReasons.length ? (
              <ol>
                {visibleReasons.slice(0, 8).map((reason, index) => (
                  <li key={reason.value}>
                    <button
                      className={selected?.value === reason.value ? "active" : ""}
                      onClick={() =>
                        updateRoute({ problem: reason.value, recordPage: 1 })
                      }
                    >
                      <span className="return-reason-rank">{index + 1}</span>
                      <div>
                        <b>{reason.label}</b>
                        <i aria-hidden="true">
                          <span
                            style={{
                              width: `${Math.max(
                                (Number(reason.record_count) / topReasonCount) * 100,
                                2,
                              )}%`,
                            }}
                          />
                        </i>
                      </div>
                      <strong>
                        {Number(reason.record_count).toLocaleString()} ·{" "}
                        {formatPercent(reason.percentage)}
                      </strong>
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="return-insight-empty">当前对象下没有匹配原因</div>
            )}
          </section>
        </aside>

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
                  <InsightStat label="相关退货" value={`${selected.record_count} 条`} />
                  <InsightStat
                    label="占有效退货"
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
                    统计包含该问题标签的去重退货记录；核心原因率表示该标签进入记录的
                    primary_label_codes，不等同于唯一责任归因。
                  </span>
                </div>
              )}

              <div className="return-diagnostic-overview">
                <section className="return-insight-card return-insight-trend">
                  <header>
                    <div>
                      <h3>{selected.label}原因占比趋势</h3>
                      <span>柱形为周退货量，折线为原因占比</span>
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
                              name === "周退货量"
                                ? [`${value} 条`, name]
                                : [
                                    `${Number(value).toFixed(1)}%（${item.payload.record_count} 条）`,
                                    `${selected.label}占比`,
                                  ]
                            }
                          />
                          <Bar
                            yAxisId="volume"
                            name="周退货量"
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
                            updateRoute({
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
                        {semanticProfile.record_count || 0} 条记录具有对应语义证据 ·
                        覆盖
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
                      onClick: () =>
                        updateRoute({ problem: item.value, recordPage: 1 }),
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
                          <p title={record.comment || record.reason}>
                            {record.comment || record.reason || "没有退货评论"}
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
                          <span className="return-part-pill">
                            {partLabel(unit.part)}
                          </span>
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
                  <div className="return-insight-empty">
                    当前原因没有可展示的评论证据
                  </div>
                )}
              </section>
            </>
          ) : (
            <div className="return-insight-empty return-diagnostic-empty">
              请选择一个退货原因开始诊断
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function InsightSelect({ label, value, values, allLabel, onChange }) {
  return (
    <label className="return-insight-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allLabel}</option>
        {filterOptions(values).map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}

function InsightStat({ label, value }) {
  return (
    <div className="return-insight-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

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

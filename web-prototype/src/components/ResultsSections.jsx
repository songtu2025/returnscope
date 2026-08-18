import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowDown, ArrowUp, Minus } from "@phosphor-icons/react";
import { formatNumber, formatPercent } from "../lib/presentation";

const COLORS = {
  green: "#16765d",
  grid: "#e7ece9",
};

function SectionCard({ title, note, action, className = "", children }) {
  return (
    <section className={`analysis-card ${className}`.trim()}>
      <header className="analysis-card-heading">
        <div>
          <h3>{title}</h3>
          {note && <p>{note}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function EmptyAnalysis({ children = "当前筛选范围没有可展示的数据" }) {
  return <div className="analysis-empty">{children}</div>;
}

function DataBars({
  rows,
  nameKey = "name",
  valueKey = "records",
  shareKey = "share",
}) {
  if (!rows?.length) return <EmptyAnalysis />;
  const maximum = Math.max(...rows.map((row) => Number(row[valueKey] ?? 0)), 1);
  return (
    <div className="analysis-bars">
      {rows.map((row, index) => (
        <div className="analysis-bar-row" key={`${row[nameKey]}-${index}`}>
          <div className="analysis-bar-label">
            <b>{row[nameKey] || "未命名"}</b>
            <span>
              {formatNumber(row[valueKey])}
              {row[shareKey] !== undefined && ` · ${formatPercent(row[shareKey])}`}
            </span>
          </div>
          <div className="analysis-bar-track" aria-hidden="true">
            <span
              style={{ width: `${Math.max((row[valueKey] / maximum) * 100, 2)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function RankedChart({ rows, ariaLabel }) {
  if (!rows?.length) return <EmptyAnalysis />;
  return (
    <div className="analysis-chart" role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows.slice(0, 8)}
          layout="vertical"
          margin={{ top: 4, right: 18, left: 14, bottom: 0 }}
        >
          <CartesianGrid stroke={COLORS.grid} horizontal={false} />
          <XAxis type="number" hide />
          <YAxis
            dataKey="name"
            type="category"
            width={84}
            tick={{ fill: "#33413a", fontSize: 11 }}
          />
          <Tooltip formatter={(value) => formatNumber(value)} />
          <Bar dataKey="records" fill={COLORS.green} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChangeValue({ value }) {
  const numeric = Number(value ?? 0);
  const Icon = numeric > 0 ? ArrowUp : numeric < 0 ? ArrowDown : Minus;
  return (
    <span className={numeric > 0 ? "is-up" : numeric < 0 ? "is-down" : ""}>
      <Icon size={13} />
      {Math.abs(numeric).toFixed(1)} pp
    </span>
  );
}

function QualityTable({ rows }) {
  if (!rows?.length) return <EmptyAnalysis />;
  return (
    <div className="analysis-table-scroll">
      <table className="analysis-table quality-table">
        <thead>
          <tr>
            <th>Listing</th>
            <th>退货记录</th>
            <th>评论覆盖</th>
            <th>标签覆盖</th>
            <th>未知语义</th>
            <th>需复核</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.listing}>
              <td className="is-strong">{row.listing}</td>
              <td>{formatNumber(row.records)}</td>
              <td>
                <RateCell value={row.text_rate} />
              </td>
              <td>
                <RateCell value={row.label_coverage} />
              </td>
              <td>
                <RateCell value={row.unknown_rate} tone="amber" />
              </td>
              <td>
                <RateCell value={row.review_rate} tone="amber" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RateCell({ value, tone = "green" }) {
  return (
    <div className={`rate-cell ${tone}`}>
      <i>
        <span style={{ width: `${Math.min(Number(value ?? 0) * 100, 100)}%` }} />
      </i>
      <small>{formatPercent(value)}</small>
    </div>
  );
}

export function OverviewSection({ overview, qualityGate }) {
  const hasProblems = Boolean(overview.top_problems?.length);
  return (
    <div className="analysis-section-stack">
      <SectionCard
        title="主要退货问题"
        note="按当前筛选范围排序，展示记录数及其退货构成占比"
      >
        {hasProblems ? (
          <DataBars rows={overview.top_problems.slice(0, 8)} />
        ) : (
          <EmptyAnalysis>
            {qualityGate?.status === "unusable"
              ? "当前结果的标签覆盖率为 0%，请先处理复核原因或使用有效模型重新分析。"
              : "当前筛选范围没有可展示的问题标签"}
          </EmptyAnalysis>
        )}
      </SectionCard>

      <SectionCard
        title="Listing 规模与证据覆盖"
        note="规模表示当前退货记录构成；覆盖率用于判断分析结果是否可直接比较"
      >
        <QualityTable rows={overview.listing_quality} />
      </SectionCard>

      <div className="analysis-grid analysis-grid-2">
        <SectionCard title="跨 Listing 问题" note="同时观察覆盖范围与集中程度">
          {overview.listing_problems?.length ? (
            <div className="analysis-table-scroll">
              <table className="analysis-table">
                <thead>
                  <tr>
                    <th>问题</th>
                    <th>记录</th>
                    <th>Listing覆盖</th>
                    <th>集中度</th>
                    <th>判断</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.listing_problems.map((row) => (
                    <tr key={row.code}>
                      <td>
                        <b>{row.name}</b>
                        <small>{row.group}</small>
                      </td>
                      <td>{formatNumber(row.records)}</td>
                      <td>{formatPercent(row.listing_coverage)}</td>
                      <td>{formatPercent(row.top_listing_share)}</td>
                      <td>
                        <span className="analysis-tag">{row.coverage_label}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyAnalysis />
          )}
        </SectionCard>
        <SectionCard title="具体部位诊断" note="排除整体与未说明，突出可定位部位">
          <DataBars rows={overview.parts} nameKey="part" />
        </SectionCard>
      </div>
    </div>
  );
}

export function DiagnosisSection({ diagnosis, onFocusProblem }) {
  const focus = diagnosis.priorities?.find(
    (item) => item.code === diagnosis.focus_code,
  );
  return (
    <div className="analysis-section-stack">
      <SectionCard
        title="问题优先级"
        note="综合问题规模、近 30 天变化、影响商品范围与核查信号"
        action={
          <label className="compact-select">
            <span>诊断问题</span>
            <select
              value={diagnosis.focus_code ?? ""}
              onChange={(event) => onFocusProblem(event.target.value)}
            >
              {diagnosis.priorities?.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name} · {formatNumber(item.records)} 条
                </option>
              ))}
            </select>
          </label>
        }
      >
        {diagnosis.priorities?.length ? (
          <div className="analysis-table-scroll">
            <table className="analysis-table priority-table">
              <thead>
                <tr>
                  <th>问题</th>
                  <th>记录数</th>
                  <th>退货构成</th>
                  <th>30天变化</th>
                  <th>影响SKU</th>
                  <th>Top SKU占比</th>
                  <th>多问题</th>
                  <th>需复核</th>
                </tr>
              </thead>
              <tbody>
                {diagnosis.priorities.map((row) => (
                  <tr
                    key={row.code}
                    className={row.code === diagnosis.focus_code ? "is-selected" : ""}
                    onClick={() => onFocusProblem(row.code)}
                  >
                    <td>
                      <b>{row.name}</b>
                      <small>{row.group}</small>
                    </td>
                    <td>{formatNumber(row.records)}</td>
                    <td>{formatPercent(row.share)}</td>
                    <td>
                      <ChangeValue value={row.change_pp} />
                    </td>
                    <td>{formatNumber(row.sku_count)}</td>
                    <td>{formatPercent(row.top_sku_share)}</td>
                    <td>{formatNumber(row.multi_problem_records)}</td>
                    <td>{formatNumber(row.review_records)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyAnalysis />
        )}
      </SectionCard>

      {focus && (
        <div className="diagnosis-summary">
          <div>
            <span>相关退货</span>
            <strong>{formatNumber(focus.records)}</strong>
            <small>占筛选退货 {formatPercent(focus.share)}</small>
          </div>
          <div>
            <span>近30天变化</span>
            <strong>{Number(focus.change_pp ?? 0).toFixed(1)} pp</strong>
            <small>与前30天相比</small>
          </div>
          <div>
            <span>影响 SKU</span>
            <strong>{formatNumber(focus.sku_count)}</strong>
            <small>Top SKU 占 {formatPercent(focus.top_sku_share)}</small>
          </div>
          <div>
            <span>需复核</span>
            <strong>{formatNumber(focus.review_records)}</strong>
            <small>含冲突与不确定结果</small>
          </div>
        </div>
      )}

      <div className="analysis-grid analysis-grid-2">
        <SectionCard title="商品定位" note="提升度高于 1 表示该商品更集中出现此问题">
          <DataBars rows={diagnosis.product_locations} shareKey="share" />
        </SectionCard>
        <SectionCard title="Amazon 原因证据">
          <DataBars rows={diagnosis.reasons} />
        </SectionCard>
        <SectionCard title="部位定位">
          <DataBars rows={diagnosis.parts} />
        </SectionCard>
        <SectionCard title="问题共现" note="提升度高于 1 表示两个问题更常共同出现">
          <DataBars rows={diagnosis.pairs} />
        </SectionCard>
      </div>

      <SectionCard
        title="评论证据"
        note={`展示 ${diagnosis.comments?.length ?? 0} 条去重评论`}
      >
        {diagnosis.comments?.length ? (
          <div className="evidence-list">
            {diagnosis.comments.map((item) => (
              <article key={item.classification_key}>
                <div>
                  <span>{item.listing || "未匹配 Listing"}</span>
                  <span>{item.sku || "无 SKU"}</span>
                  <span>{item.reason || "无 Amazon 原因"}</span>
                </div>
                <p>{item.comment}</p>
                {item.evidence && <blockquote>{item.evidence}</blockquote>}
              </article>
            ))}
          </div>
        ) : (
          <EmptyAnalysis />
        )}
      </SectionCard>
    </div>
  );
}

export function ProductsSection({ products, onDimension }) {
  const dimensionLabels = {
    listing: "Listing",
    category_b: "品类B",
    sku: "SKU",
    asin: "ASIN",
  };
  const matrix = products.matrix ?? [];
  const labels = matrix[0]?.values?.map((item) => item.label) ?? [];
  const maximum = Math.max(
    ...matrix.flatMap((row) => row.values.map((item) => item.records)),
    1,
  );
  return (
    <div className="analysis-section-stack">
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
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyAnalysis />
        )}
      </SectionCard>

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
    </div>
  );
}

export function QualitySection({ quality }) {
  return (
    <div className="analysis-section-stack">
      <div className="quality-kpis">
        <div>
          <span>复核评论组合</span>
          <strong>{formatNumber(quality.metrics.review_comments)}</strong>
          <small>去重后需人工判断</small>
        </div>
        <div>
          <span>原因方向冲突</span>
          <strong>{formatNumber(quality.metrics.conflicts)}</strong>
          <small>需要核对语义方向</small>
        </div>
        <div>
          <span>未知语义记录</span>
          <strong>{formatNumber(quality.metrics.unknown_records)}</strong>
          <small>尚未映射到标签体系</small>
        </div>
      </div>

      <SectionCard title="按 Listing 的证据与分类覆盖">
        <QualityTable rows={quality.listing_quality} />
      </SectionCard>

      <div className="analysis-grid analysis-grid-2">
        <SectionCard title="处理状态">
          <RankedChart rows={quality.statuses} ariaLabel="处理状态分布" />
        </SectionCard>
        <SectionCard title="主要复核原因">
          <DataBars rows={quality.review_reasons} />
        </SectionCard>
      </div>

      <SectionCard title="未知语义" note="用于扩充标签体系和提示词规则">
        {quality.unknowns?.length ? (
          <div className="analysis-table-scroll">
            <table className="analysis-table">
              <thead>
                <tr>
                  <th>记录</th>
                  <th>Amazon原因</th>
                  <th>评论</th>
                  <th>未知观点</th>
                  <th>未映射原因</th>
                </tr>
              </thead>
              <tbody>
                {quality.unknowns.map((row, index) => (
                  <tr key={`${row.comment}-${index}`}>
                    <td>{formatNumber(row.records)}</td>
                    <td>{row.reason}</td>
                    <td className="wide-cell">{row.comment}</td>
                    <td>{row.opinion}</td>
                    <td>{row.unmapped_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyAnalysis>当前筛选范围没有未知语义</EmptyAnalysis>
        )}
      </SectionCard>
    </div>
  );
}

export function DetailsSection({ details, onPage, downloadUrl }) {
  return (
    <SectionCard
      title="数据明细"
      note={`当前筛选共 ${formatNumber(details.total)} 条记录`}
      action={
        <a className="secondary-button" href={downloadUrl}>
          导出当前筛选
        </a>
      }
    >
      {details.records?.length ? (
        <>
          <div className="analysis-table-scroll detail-table-scroll">
            <table className="analysis-table detail-table">
              <thead>
                <tr>
                  <th>退货日期</th>
                  <th>SKU</th>
                  <th>ASIN</th>
                  <th>Listing</th>
                  <th>品类B</th>
                  <th>Amazon原因</th>
                  <th>主因标签</th>
                  <th>处理状态</th>
                  <th>评论</th>
                </tr>
              </thead>
              <tbody>
                {details.records.map((row, index) => (
                  <tr key={`${row.order_id}-${index}`}>
                    <td>{String(row.return_date ?? "").slice(0, 10)}</td>
                    <td>{row.sku}</td>
                    <td>{row.asin}</td>
                    <td>{row.listing}</td>
                    <td>{row.category_b}</td>
                    <td>{row.reason}</td>
                    <td>{row.primary_labels || row.problem_labels}</td>
                    <td>
                      <span className="analysis-tag">{row.status}</span>
                    </td>
                    <td className="comment-cell">{row.comment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination-bar">
            <span>
              第 {details.page} / {details.pages} 页
            </span>
            <div>
              <button
                disabled={details.page <= 1}
                onClick={() => onPage(details.page - 1)}
              >
                上一页
              </button>
              <button
                disabled={details.page >= details.pages}
                onClick={() => onPage(details.page + 1)}
              >
                下一页
              </button>
            </div>
          </div>
        </>
      ) : (
        <EmptyAnalysis />
      )}
    </SectionCard>
  );
}

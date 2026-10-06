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
import { formatNumber, formatPercent } from "../../lib/presentation";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisBarRow} AnalysisBarRow */
/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisQualityRow} AnalysisQualityRow */

const COLORS = {
  green: "#16765d",
  grid: "#e7ece9",
};

/** @param {{title: import("react").ReactNode, note?: import("react").ReactNode, action?: import("react").ReactNode, className?: string, children: import("react").ReactNode}} props */
export function SectionCard({ title, note, action, className = "", children }) {
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

/** @param {{children?: import("react").ReactNode}} props */
export function EmptyAnalysis({ children = "当前筛选范围没有可展示的数据" }) {
  return <div className="analysis-empty">{children}</div>;
}

/**
 * @param {{rows: AnalysisBarRow[], nameKey?: string, valueKey?: string, shareKey?: string}} props
 */
export function DataBars({
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
              style={{
                width: `${Math.max((Number(row[valueKey] ?? 0) / maximum) * 100, 2)}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** @param {{rows: AnalysisBarRow[], ariaLabel: string}} props */
export function RankedChart({ rows, ariaLabel }) {
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

/** @param {{value: unknown}} props */
export function ChangeValue({ value }) {
  const numeric = Number(value ?? 0);
  const Icon = numeric > 0 ? ArrowUp : numeric < 0 ? ArrowDown : Minus;
  return (
    <span className={numeric > 0 ? "is-up" : numeric < 0 ? "is-down" : ""}>
      <Icon size={13} />
      {Math.abs(numeric).toFixed(1)} pp
    </span>
  );
}

/** @param {{rows: AnalysisQualityRow[]}} props */
export function QualityTable({ rows }) {
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

/** @param {{value: unknown, tone?: string}} props */
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

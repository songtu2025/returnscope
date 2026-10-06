import { formatNumber } from "../../lib/presentation";
import {
  SectionCard,
  EmptyAnalysis,
  DataBars,
  QualityTable,
  RankedChart,
} from "./LegacyAnalysisDisplay";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisQuality} AnalysisQuality */

/** @param {{metrics: AnalysisQuality["metrics"]}} props */
function QualityMetrics({ metrics }) {
  return (
    <div className="quality-kpis">
      <div>
        <span>复核评论组合</span>
        <strong>{formatNumber(metrics.review_comments)}</strong>
        <small>去重后需人工判断</small>
      </div>
      <div>
        <span>原因方向冲突</span>
        <strong>{formatNumber(metrics.conflicts)}</strong>
        <small>需要核对语义方向</small>
      </div>
      <div>
        <span>未知语义记录</span>
        <strong>{formatNumber(metrics.unknown_records)}</strong>
        <small>尚未映射到标签体系</small>
      </div>
    </div>
  );
}

/** @param {{rows: AnalysisQuality["unknowns"]}} props */
function QualityUnknowns({ rows }) {
  return (
    <SectionCard title="未知语义" note="用于扩充标签体系和提示词规则">
      {rows?.length ? (
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
              {rows.map((row, index) => (
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
  );
}

/** @param {{quality: AnalysisQuality}} props */
export function QualitySection({ quality }) {
  return (
    <div className="analysis-section-stack">
      <QualityMetrics metrics={quality.metrics} />

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

      <QualityUnknowns rows={quality.unknowns} />
    </div>
  );
}

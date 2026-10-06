import { formatNumber, formatPercent } from "../../lib/presentation";
import {
  SectionCard,
  EmptyAnalysis,
  DataBars,
  QualityTable,
} from "./LegacyAnalysisDisplay";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisOverview} AnalysisOverview */

/** @param {{rows: AnalysisOverview["listing_problems"]}} props */
function CrossListingProblems({ rows }) {
  return (
    <SectionCard title="跨 Listing 问题" note="同时观察覆盖范围与集中程度">
      {rows?.length ? (
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
              {rows.map((row) => (
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
  );
}

/** @param {{overview: AnalysisOverview, qualityGate?: {status?: string} | null}} props */
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
        <CrossListingProblems rows={overview.listing_problems} />
        <SectionCard title="具体部位诊断" note="排除整体与未说明，突出可定位部位">
          <DataBars rows={overview.parts} nameKey="part" />
        </SectionCard>
      </div>
    </div>
  );
}

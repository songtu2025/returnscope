import { formatNumber } from "../../lib/presentation";
import { SectionCard, EmptyAnalysis } from "./LegacyAnalysisDisplay";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisDetails} AnalysisDetails */

/** @param {{rows: NonNullable<AnalysisDetails["records"]>}} props */
function DetailsTable({ rows }) {
  return (
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
          {rows.map((row, index) => (
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
  );
}

/** @param {{details: AnalysisDetails, onPage: (page: number) => void}} props */
function DetailsPagination({ details, onPage }) {
  return (
    <div className="pagination-bar">
      <span>
        第 {details.page} / {details.pages} 页
      </span>
      <div>
        <button disabled={details.page <= 1} onClick={() => onPage(details.page - 1)}>
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
  );
}

/** @param {{details: AnalysisDetails, onPage: (page: number) => void, downloadUrl: string}} props */
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
          <DetailsTable rows={details.records} />
          <DetailsPagination details={details} onPage={onPage} />
        </>
      ) : (
        <EmptyAnalysis />
      )}
    </SectionCard>
  );
}

import { MysqlPreviewToggle } from "./MysqlPreviewToggle";
import { Fragment, useState } from "react";

/** @typedef {import("./mysqlReturnContracts").MysqlPreviewRow} MysqlPreviewRow */
/** @typedef {import("./mysqlReturnContracts").MysqlField} MysqlField */

/** @param {{ rows: MysqlPreviewRow[], fields: MysqlField[] }} props */
export function MysqlPreviewTable({ rows, fields }) {
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState(/** @type {number | null} */ (null));
  const pageSize = 5;
  const start = page * pageSize;
  const end = Math.min(start + pageSize, rows.length);
  /** @param {number} next */
  const changePage = (next) => {
    setPage(next);
    setExpanded(null);
  };

  return (
    <div className="mysql-preview-records">
      <table aria-label="用户反馈数据样例" className="mysql-preview-table">
        <colgroup>
          <col className="mysql-preview-date-col" />
          <col className="mysql-preview-product-col" />
          <col className="mysql-preview-quantity-col" />
          <col className="mysql-preview-reason-col" />
          <col />
          <col className="mysql-preview-action-col" />
        </colgroup>
        <thead>
          <tr>
            {["反馈日期", "商品 / 店铺", "数量", "来源原因", "反馈原文", "操作"].map(
              (label) => (
                <th key={label} scope="col">
                  {label}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.slice(start, end).map((row, offset) => {
            const index = start + offset;
            const isExpanded = expanded === index;
            const [date, time] = String(row["return-date"] || "—").split(/[T ]/);
            return (
              <Fragment key={index}>
                <tr>
                  <td className="mysql-preview-date">
                    <span>{date}</span>
                    {time && <small>{time}</small>}
                  </td>
                  <td>
                    <strong className="mysql-preview-excerpt">{row.sku || "—"}</strong>
                    <small className="mysql-preview-excerpt">
                      {row["店铺/站点"] || "未提供店铺"}
                    </small>
                  </td>
                  <td className="mysql-preview-quantity">{row.quantity ?? "—"}</td>
                  <td>
                    <span className="mysql-preview-excerpt">
                      {String(row.reason || "未提供").replaceAll("_", " ")}
                    </span>
                  </td>
                  <td>
                    <span className="mysql-preview-excerpt">
                      {row["customer-comments"] || "未填写反馈"}
                    </span>
                  </td>
                  <td>
                    <MysqlPreviewToggle
                      index={index}
                      isExpanded={isExpanded}
                      setExpanded={setExpanded}
                    />
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="mysql-preview-detail-row">
                    <td colSpan={6}>
                      <dl
                        id={`mysql-preview-detail-${index}`}
                        aria-label={`第${index + 1}条完整记录`}
                      >
                        {fields.map((field) => (
                          <div
                            key={field.name}
                            className={
                              field.name === "customer-comments" ||
                              field.name === "product-name"
                                ? "mysql-preview-detail-wide"
                                : undefined
                            }
                          >
                            <dt>{field.label}</dt>
                            <dd>{String(row[field.name] ?? "") || "—"}</dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="mysql-preview-pagination">
        <span>
          样例 {start + 1}–{end} / {rows.length} 条 · 导入范围不受分页影响
        </span>
        {rows.length > pageSize && (
          <div>
            <button
              type="button"
              className="secondary-button"
              disabled={page === 0}
              onClick={() => changePage(page - 1)}
            >
              上一页
            </button>
            <span>
              {page + 1} / {Math.ceil(rows.length / pageSize)}
            </span>
            <button
              type="button"
              className="secondary-button"
              disabled={end === rows.length}
              onClick={() => changePage(page + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import AntPagination from "antd/es/pagination";

import { PAGE_SIZES } from "../shared/pagination";
import { AntdProvider } from "./AntdProvider";

/**
 * @param {{
 *   page: number,
 *   pageSize: number,
 *   total: number,
 *   totalPages: number,
 *   onPage: (page: number) => void,
 *   onPageSize: (pageSize: number) => void,
 * }} props
 */
export function Pagination({ page, pageSize, total, totalPages, onPage, onPageSize }) {
  return (
    <AntdProvider>
      <AntPagination
        className="result-pagination"
        role="navigation"
        aria-label={`分页，第 ${page} 页，共 ${totalPages} 页`}
        current={page}
        pageSize={pageSize}
        total={total}
        pageSizeOptions={PAGE_SIZES}
        showLessItems
        showSizeChanger={{ "aria-label": "每页数量", showSearch: false }}
        showTotal={(value) => `共 ${Number(value || 0).toLocaleString()} 条`}
        itemRender={(_itemPage, type, element) => {
          if (type === "prev") {
            return (
              <button
                type="button"
                className="ant-pagination-item-link"
                aria-label="上一页"
                tabIndex={-1}
              >
                <CaretLeft aria-hidden="true" />
              </button>
            );
          }
          if (type === "next") {
            return (
              <button
                type="button"
                className="ant-pagination-item-link"
                aria-label="下一页"
                tabIndex={-1}
              >
                <CaretRight aria-hidden="true" />
              </button>
            );
          }
          return element;
        }}
        onChange={(nextPage, nextPageSize) => {
          if (nextPageSize === pageSize) onPage(nextPage);
        }}
        onShowSizeChange={(_current, nextPageSize) => onPageSize(nextPageSize)}
      />
    </AntdProvider>
  );
}

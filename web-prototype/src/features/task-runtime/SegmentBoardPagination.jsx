import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import Button from "antd/es/button";

/**
 * @param {{total: number, pageSize: number, page: number, totalPages: number,
 * setPage: import("react").Dispatch<import("react").SetStateAction<number>>}} props
 */
export function SegmentBoardPagination({ total, pageSize, page, totalPages, setPage }) {
  return (
    <footer className="listing-table-footer">
      <span>共 {total} 条</span>
      <div>
        <span>{pageSize} 条/页</span>
        <Button
          type="text"
          className="icon-button"
          aria-label="上一页"
          disabled={page <= 1}
          onClick={() => setPage((current) => Math.max(current - 1, 1))}
        >
          <CaretLeft size={15} />
        </Button>
        <b>{page}</b>
        <Button
          type="text"
          className="icon-button"
          aria-label="下一页"
          disabled={page >= totalPages}
          onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
        >
          <CaretRight size={15} />
        </Button>
      </div>
    </footer>
  );
}

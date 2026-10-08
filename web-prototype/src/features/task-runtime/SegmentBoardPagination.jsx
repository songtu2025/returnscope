import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { useRef } from "react";

/**
 * @param {{total: number, pageSize: number, page: number, totalPages: number,
 * setPage: import("react").Dispatch<import("react").SetStateAction<number>>}} props
 */
export function SegmentBoardPagination({ total, pageSize, page, totalPages, setPage }) {
  const pageRef = useRef(/** @type {HTMLElement | null} */ (null));
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
          onClick={() => {
            if (page === 2) pageRef.current?.focus();
            setPage((current) => Math.max(current - 1, 1));
          }}
        >
          <CaretLeft size={15} />
        </Button>
        <b ref={pageRef} tabIndex={-1} aria-label={`第 ${page} 页`}>
          {page}
        </b>
        <Button
          type="text"
          className="icon-button"
          aria-label="下一页"
          disabled={page >= totalPages}
          onClick={() => {
            if (page + 1 === totalPages) pageRef.current?.focus();
            setPage((current) => Math.min(current + 1, totalPages));
          }}
        >
          <CaretRight size={15} />
        </Button>
      </div>
    </footer>
  );
}

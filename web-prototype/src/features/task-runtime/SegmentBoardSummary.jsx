import { WarningCircle } from "@phosphor-icons/react";

/** @param {{count: number}} props */
export function SegmentBoardHeader({ count }) {
  return (
    <div className="listing-queue-header">
      <div>
        <h3>
          Listing 明细 <span>{count}</span>
        </h3>
      </div>
    </div>
  );
}

/** @param {{count: number, excludedRecords: number, excludedComments: number}} props */
export function ExcludedListingsSummary({ count, excludedRecords, excludedComments }) {
  return (
    <>
      {count > 0 && (
        <div className="excluded-listing-summary">
          <WarningCircle size={18} />
          <div>
            <b>未配置品类的数据未纳入语义分析</b>
            <p>
              {excludedRecords.toLocaleString()} 条记录 /{" "}
              {excludedComments.toLocaleString()}
              组评论，不创建 Listing 执行项，也不会调用模型。
            </p>
          </div>
        </div>
      )}
    </>
  );
}

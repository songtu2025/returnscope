import { ListChecks } from "@phosphor-icons/react";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { ReviewBatchError } from "./ReviewBatchError";
import { ReviewRecordRow } from "./ReviewRecordComponents";
import { itemId } from "./reviewRecordDrafts";

/** @typedef {import("./reviewWorkspaceContracts").ReviewWorkspaceContext} ReviewWorkspaceContext */

/** @param {ReviewWorkspaceContext} context */
export function ReviewRecordTable(context) {
  const { route, updateRoute, recordsState, records, recordItems, totalPages } =
    context;
  return (
    <section className="review-record-card">
      <ReviewRecordStatus {...context} />
      {recordItems.length > 0 && !recordsState.error && (
        <>
          <ReviewRecordRows {...context} />
          <Pagination
            page={route.page}
            pageSize={route.pageSize}
            total={records?.total ?? 0}
            totalPages={totalPages}
            onPage={(/** @type {number} */ page) => updateRoute({ page })}
            onPageSize={(/** @type {number} */ pageSize) =>
              updateRoute({ page: 1, pageSize })
            }
          />
        </>
      )}
    </section>
  );
}

function ReviewRecordTableHead() {
  return (
    <div className="review-record-table-head" role="row">
      <span>order-id / 产品名称</span>
      <span>Listing / 产品SKU</span>
      <span>退货SKU（MSKU）</span>
      <span>分类结果</span>
      <span>状态 / 操作</span>
    </div>
  );
}

/** @param {ReviewWorkspaceContext} context */
function ReviewRecordRows(context) {
  const { recordItems, recordsState, openRecord } = context;
  return (
    <div className={`review-record-table ${recordsState.loading ? "is-loading" : ""}`}>
      <ReviewRecordTableHead />
      {recordItems.map((record) => (
        <ReviewRecordRow
          key={itemId(record)}
          record={record}
          onOpen={() => openRecord(record)}
        />
      ))}
    </div>
  );
}

/** @param {ReviewWorkspaceContext} context */
function ReviewRecordStatus({ recordsState, records, recordItems, loadRecords }) {
  return (
    <>
      {" "}
      {recordsState.loading && !records && <InlineLoading label="正在读取复核记录…" />}
      {recordsState.error && (
        <ReviewBatchError error={recordsState.error} onRetry={loadRecords} />
      )}
      {!recordsState.loading && !recordsState.error && recordItems.length === 0 && (
        <EmptyState
          icon={ListChecks}
          title="当前条件没有复核记录"
          description="调整处理状态或业务字段后重新查询。"
        />
      )}
    </>
  );
}

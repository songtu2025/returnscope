import Button from "antd/es/button";
import Input from "antd/es/input";
import { useId } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { Pagination, ResultError } from "./ClassificationResultCommon";
import { ResultRecordRow } from "./ClassificationResultDetailParts";
import { ResultRecordFilters } from "./ResultRecordFilters";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailRecords(context) {
  const {
    route,
    result,
    records,
    recordsLoading,
    recordsError,
    retryRecords,
    openEvidence,
    isUserFeedback,
    totalPages,
    changeRecordPage,
    changePageSize,
  } = context;
  return (
    <section className="result-record-card" id="classification-order-records">
      <ResultRecordHeading {...context} />

      {recordsError && <ResultError message={recordsError} onRetry={retryRecords} />}
      {recordsLoading && !records && <InlineLoading label="正在读取订单记录…" />}
      {!recordsError && !recordsLoading && records?.items?.length === 0 && (
        <ResultRecordEmpty isUserFeedback={isUserFeedback} />
      )}
      {records && records.items.length > 0 && (
        <>
          <div className={`result-record-table ${recordsLoading ? "is-loading" : ""}`}>
            <ResultRecordColumnHead {...context} />
            {records.items.map((group) => (
              <ResultRecordRow
                key={group.record.source_record_id}
                group={group}
                analysisContext={result.analysis_context}
                onOpen={openEvidence(group)}
              />
            ))}
          </div>
          <Pagination
            page={route.recordPage}
            pageSize={route.pageSize}
            total={records.total}
            totalPages={totalPages}
            onPage={changeRecordPage}
            onPageSize={changePageSize}
          />
        </>
      )}
    </section>
  );
}

/** @param {{isUserFeedback: boolean}} props */
function ResultRecordEmpty({ isUserFeedback }) {
  return (
    <EmptyState
      icon={MagnifyingGlass}
      title={isUserFeedback ? "当前条件没有反馈记录" : "当前条件没有订单记录"}
      description="调整筛选条件后重试，也可清除上方的结果筛选。"
    />
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultRecordHeading(context) {
  const { updateRoute, orderInput, setOrderInput, isUserFeedback } = context;
  const orderInputId = useId();
  return (
    <header>
      <div className="result-record-heading">
        <b>{isUserFeedback ? "用户反馈记录" : "订单级分类记录"}</b>
      </div>
      <div className="result-record-tools">
        <ResultRecordFilters {...context}>
          <div className="record-order-search">
            <div className="result-record-field">
              <label htmlFor={orderInputId}>订单号</label>
              <Input
                id={orderInputId}
                aria-label="搜索 order-id"
                placeholder="输入 order-id 精确查询"
                value={orderInput}
                onChange={(event) => setOrderInput(event.target.value)}
                onPressEnter={() =>
                  updateRoute({ orderId: orderInput.trim(), recordPage: 1 })
                }
              />
            </div>
            <Button
              onClick={() => updateRoute({ orderId: orderInput.trim(), recordPage: 1 })}
            >
              查询
            </Button>
          </div>
        </ResultRecordFilters>
      </div>
    </header>
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultRecordColumnHead(context) {
  const { isUserFeedback } = context;
  return (
    <div className="result-record-head" role="row">
      <span>{isUserFeedback ? "记录ID / 日期" : "order-id"}</span>
      <span>{isUserFeedback ? "来源SKU（MSKU）" : "退货SKU（MSKU）"}</span>
      <span>产品名称 / 产品SKU</span>
      <span>{isUserFeedback ? "反馈标题 / 正文" : "Amazon原因"}</span>
      <span>{isUserFeedback ? "语义结果" : "分类结果"}</span>
      <span>重跑标记</span>
      <span>操作</span>
    </div>
  );
}

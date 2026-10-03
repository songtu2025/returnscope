import Button from "antd/es/button";
import Input from "antd/es/input";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { Pagination } from "./ClassificationResultCommon";
import { ResultRecordRow } from "./ClassificationResultDetailParts";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailRecords(context) {
  const {
    route,
    result,
    records,
    recordsLoading,
    openEvidence,
    isUserFeedback,
    totalPages,
    changeRecordPage,
    changePageSize,
  } = context;
  return (
    <section className="result-record-card" id="classification-order-records">
      <ResultRecordHeading {...context} />

      {recordsLoading && !records && <InlineLoading label="正在读取订单记录…" />}
      {!recordsLoading && records?.items?.length === 0 && (
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
      description="调整问题、产品名称、产品SKU或order-id后重试。"
    />
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultRecordHeading(context) {
  const { updateRoute, records, orderInput, setOrderInput, isUserFeedback } = context;
  return (
    <header>
      <div>
        <b>{isUserFeedback ? "用户反馈记录" : "订单级分类记录"}</b>
        <span>
          {Number(records?.total || 0).toLocaleString()} 组反馈 · 关联
          {Number(records?.source_total || 0).toLocaleString()} 条源明细
        </span>
      </div>
      <div className="record-order-search">
        <Input
          aria-label="搜索 order-id"
          placeholder="输入 order-id 精确查询"
          value={orderInput}
          onChange={(event) => setOrderInput(event.target.value)}
          onPressEnter={() =>
            updateRoute({ orderId: orderInput.trim(), recordPage: 1 })
          }
        />
        <Button
          onClick={() => updateRoute({ orderId: orderInput.trim(), recordPage: 1 })}
        >
          查询
        </Button>
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
      <span>操作</span>
    </div>
  );
}

/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @type {Record<string, string>} */
const DIAGNOSTIC_DOMAIN_LABELS = {
  SEMANTIC_ANALYSIS_QUALITY: "语义分析差异",
  TECHNICAL_CONFIGURATION: "配置异常",
  TECHNICAL_RUNTIME: "运行异常",
};

/** @type {Record<string, string>} */
const DIAGNOSTIC_DETAIL_STATUS_LABELS = {
  AVAILABLE: "诊断明细已保留",
  NOT_APPLICABLE: "不涉及业务语义差异",
  NOT_RETAINED: "诊断明细未保留",
};

/** @param {{item: SemanticReviewLedgerItem, suggestedAction: string}} props */
export function DiagnosticDetails({ item, suggestedAction }) {
  const systemFailure = ["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition);
  if (
    !systemFailure &&
    !item.diagnosticDomain &&
    !item.diagnosticCode &&
    !item.diagnosticTitle
  ) {
    return null;
  }
  const domainLabel = DIAGNOSTIC_DOMAIN_LABELS[item.diagnosticDomain] || "系统诊断";
  const detailStatus =
    DIAGNOSTIC_DETAIL_STATUS_LABELS[item.detailStatus] || item.detailStatus;

  return (
    <div className="semantic-review-diagnostic">
      <DiagnosticHeading
        item={item}
        domainLabel={domainLabel}
        detailStatus={detailStatus}
      />
      <DiagnosticResults item={item} />
      <p>
        <b>处理建议</b>
        <span>{item.diagnosticAction || suggestedAction}</span>
      </p>
    </div>
  );
}

/** @param {Pick<Parameters<typeof DiagnosticDetails>[0] & {domainLabel:string,detailStatus:string}, "item" | "domainLabel" | "detailStatus">} props */
function DiagnosticHeading({ item, domainLabel, detailStatus }) {
  return (
    <div className="semantic-review-diagnostic-heading">
      <b>{item.diagnosticTitle || item.opinion}</b>
      <small>
        {domainLabel}
        {item.diagnosticCode ? ` · ${item.diagnosticCode}` : ""}
        {detailStatus ? ` · ${detailStatus}` : ""}
      </small>
    </div>
  );
}
/** @param {{item: import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem}} props */
function DiagnosticResults({ item }) {
  return (
    <dl>
      <div>
        <dt>首次结果</dt>
        <dd>{item.primaryResult || "未提供"}</dd>
      </div>
      <div>
        <dt>复核结果</dt>
        <dd>{item.secondaryResult || "未提供"}</dd>
      </div>
      <div>
        <dt>差异说明</dt>
        <dd>{item.diagnosticDetail || item.reason || "未提供"}</dd>
      </div>
    </dl>
  );
}

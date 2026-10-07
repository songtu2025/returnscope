import { Pagination } from "../../components/Pagination";
import {
  formatDate,
  partLabel,
  selectedSemanticUnit,
} from "./returnReasonInsightPresentation";
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").InsightEvidence} InsightEvidence */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{record: DashboardRecord, selected: InsightReason, terms: AnalysisContextTerms, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} props */
function EvidenceRow({ record, selected, terms, onEvidence }) {
  const unit = selectedSemanticUnit(record, selected.value);
  return (
    <article>
      <p title={record.comment || record.reason || undefined}>
        {record.comment || record.reason || terms.missingText}
      </p>
      <div>
        <b>{unit.opinion || selected.label}</b>
        <small>{formatDate(record.return_date)}</small>
      </div>
      <div>
        <b>{record.product_name || "未提供产品"}</b>
        <small>{record.product_sku || record.source_sku || "未提供 SKU"}</small>
      </div>
      <span className="return-part-pill">{partLabel(unit.part)}</span>
      <button
        className="text-button"
        onClick={(event) => onEvidence(record, event.currentTarget)}
      >
        查看证据
      </button>
    </article>
  );
}

/** @param {{evidence: InsightEvidence, selected: InsightReason, terms: AnalysisContextTerms, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} props */
function EvidenceTable({ evidence, selected, terms, onEvidence }) {
  return (
    <div className="return-insight-evidence-table">
      <div className="return-insight-evidence-head">
        <span>原始评论</span>
        <span>中文意见</span>
        <span>产品 / SKU</span>
        <span>部位</span>
        <span />
      </div>
      {evidence.items.map((record) => (
        <EvidenceRow
          key={record.id || record.source_record_id}
          record={record}
          selected={selected}
          terms={terms}
          onEvidence={onEvidence}
        />
      ))}
    </div>
  );
}

function EvidenceLoading() {
  return (
    <div className="return-insight-empty" role="status">
      正在加载语义证据…
    </div>
  );
}

/** @param {{evidenceError: string, onEvidenceRetry: () => void}} props */
function EvidenceError({ evidenceError, onEvidenceRetry }) {
  return (
    <div className="return-insight-empty" role="alert">
      <span>证据加载失败：{evidenceError}</span>
      <button type="button" className="text-button" onClick={onEvidenceRetry}>
        重试
      </button>
    </div>
  );
}

/** @param {{evidence: InsightEvidence, selected: InsightReason, terms: AnalysisContextTerms, evidenceLoading: boolean, evidenceError: string, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void, onEvidenceRetry: () => void}} props */
function EvidenceContent(props) {
  if (props.evidenceLoading) return <EvidenceLoading />;
  if (props.evidenceError)
    return (
      <EvidenceError
        evidenceError={props.evidenceError}
        onEvidenceRetry={props.onEvidenceRetry}
      />
    );
  if (props.evidence.items?.length)
    return (
      <EvidenceTable
        evidence={props.evidence}
        selected={props.selected}
        terms={props.terms}
        onEvidence={props.onEvidence}
      />
    );
  return <div className="return-insight-empty">当前原因没有可展示的评论证据</div>;
}

/** @param {{selected: InsightReason, evidence: InsightEvidence, evidencePage: number, evidenceLoading: boolean, evidenceError: string, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void, onEvidencePage: (page: number) => void, onEvidenceRetry: () => void, terms: AnalysisContextTerms}} props */
export function ReturnReasonDiagnosticEvidence({
  selected,
  evidence,
  evidencePage,
  evidenceLoading,
  evidenceError,
  onEvidence,
  onEvidencePage,
  onEvidenceRetry,
  terms,
}) {
  const evidencePageSize = evidence.page_size || 10;
  const evidencePageCount = Math.max(1, Math.ceil(evidence.total / evidencePageSize));
  return (
    <section
      className={`return-insight-card return-insight-evidence${evidence.total > evidencePageSize ? " is-paginated" : ""}`}
      aria-busy={evidenceLoading}
    >
      <header>
        <div>
          <h3>语义证据</h3>
          <span>原始评论与结构化语义单元一一对应</span>
        </div>
        <b>共 {Number(evidence.total || 0).toLocaleString()} 条</b>
      </header>
      <EvidenceContent
        evidence={evidence}
        selected={selected}
        terms={terms}
        evidenceLoading={evidenceLoading}
        evidenceError={evidenceError}
        onEvidence={onEvidence}
        onEvidenceRetry={onEvidenceRetry}
      />
      {evidence.total > evidencePageSize && (
        <Pagination
          page={evidencePage}
          pageSize={evidencePageSize}
          total={evidence.total}
          totalPages={evidencePageCount}
          onPage={onEvidencePage}
          disabled={evidenceLoading}
          showTotal={false}
          showQuickJumper={evidencePageCount > 20}
        />
      )}
    </section>
  );
}

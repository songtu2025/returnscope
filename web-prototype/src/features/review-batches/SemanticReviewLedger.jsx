import { useMemo, useState } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import {
  CheckCircle,
  PencilSimple,
  Plus,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";

import { labelText } from "../../lib/taxonomyPresentation";
import {
  dispositionTone,
  effectiveReviewItem,
  REVIEW_DISPOSITION_LABELS,
  semanticReviewLedger,
} from "./semanticReviewPresentation";

/**
 * @typedef {import("../../shared/api/reviewBatchContracts").AddedSemanticItem} AddedSemanticItem
 * @typedef {import("../../shared/api/reviewBatchContracts").CoverageStatus} CoverageStatus
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewAction} SemanticReviewAction
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem
 */

/** @type {Record<string, string>} */
const ACTION_LABELS = {
  change_label: "修改标签",
  remove: "删除错误提取",
  no_tag_needed: "标记为无需归类",
};

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

/** @param {SemanticReviewLedgerItem} item @param {ReviewLabel[]} labels */
function labelDisplay(item, labels) {
  const label = labels.find((candidate) => candidate.code === item.labelCode);
  if (label) return labelText(label);
  if (item.labelPath?.length) return item.labelPath.join(" → ");
  return item.labelCode || "未设置标签";
}

/** @param {AddedSemanticItem} item @param {number} index @returns {SemanticReviewLedgerItem} */
function manualItem(item, index) {
  return {
    id: item.item_id || `manual-${index + 1}`,
    evidence: item.evidence_text,
    evidenceSource: "COMMENT",
    opinion: item.opinion,
    labelCode: item.label_code,
    labelPath: [],
    disposition: "MAPPED",
    reason: item.note || "人工补充的遗漏观点",
    diagnosticDomain: "",
    diagnosticCode: "",
    diagnosticTitle: "",
    detailStatus: "",
    primaryResult: "",
    secondaryResult: "",
    diagnosticDetail: "",
    diagnosticAction: "",
    businessReviewRequired: true,
    manual: true,
  };
}

/** @param {SemanticItemReview[]} items @param {SemanticItemReview} next */
function upsert(items, next) {
  const existing = items.findIndex(
    (item) => item.semantic_item_id === next.semantic_item_id,
  );
  if (existing < 0) return [...items, next];
  return items.map((item, index) => (index === existing ? next : item));
}

/** @param {AddedSemanticItem[]} items */
function nextManualId(items) {
  let index = items.length + 1;
  while (items.some((item) => item.item_id === `manual-${index}`)) index += 1;
  return `manual-${index}`;
}

/** @param {{item: SemanticReviewLedgerItem}} props */
function DiagnosticDetails({ item }) {
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
      <div className="semantic-review-diagnostic-heading">
        <b>{item.diagnosticTitle || item.opinion}</b>
        <small>
          {domainLabel}
          {item.diagnosticCode ? ` · ${item.diagnosticCode}` : ""}
          {detailStatus ? ` · ${detailStatus}` : ""}
        </small>
      </div>
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
      <p>
        <b>处理建议</b>
        <span>{item.diagnosticAction || "请联系管理员检查并重新运行。"}</span>
      </p>
    </div>
  );
}

/** @param {{item: SemanticReviewLedgerItem, labels: ReviewLabel[], editable: boolean, review?: SemanticItemReview, onReview: (review: SemanticItemReview) => void, onReset: () => void}} props */
function ReviewLedgerItem({ item, labels, editable, review, onReview, onReset }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => ({
    action: /** @type {SemanticReviewAction} */ (review?.action || "change_label"),
    label_code: review?.label_code || item.labelCode || "",
    note: review?.note || "",
  }));
  const effective = effectiveReviewItem(item, review);
  const removed = item.businessReviewRequired !== false && review?.action === "remove";
  const tone = removed ? "informational" : dispositionTone(effective.disposition);
  const statusLabel = removed
    ? "已标记删除"
    : REVIEW_DISPOSITION_LABELS[effective.disposition] || effective.disposition;

  const saveDraft = () => {
    onReview({
      semantic_item_id: item.id,
      action: draft.action,
      label_code: draft.action === "change_label" ? draft.label_code : null,
      note: draft.note.trim() || null,
    });
    setEditing(false);
  };

  return (
    <article
      className={`semantic-review-item is-${tone} ${removed ? "is-removed" : ""}`}
    >
      <div className="semantic-review-evidence">
        <span>{item.evidenceSource || "原评论"}</span>
        <blockquote>“{item.evidence}”</blockquote>
      </div>
      <div className="semantic-review-opinion">
        <span>{item.manual ? "人工补充观点" : "提取观点"}</span>
        <p>{item.opinion}</p>
        {item.reason && <small>{item.reason}</small>}
      </div>
      <div className="semantic-review-decision">
        <span className={`semantic-review-state is-${tone}`}>{statusLabel}</span>
        {!removed && effective.disposition === "MAPPED" && (
          <b>{labelDisplay(effective, labels)}</b>
        )}
        {!removed && effective.disposition !== "MAPPED" && effective.reason && (
          <small>{effective.reason}</small>
        )}
        {review &&
          item.businessReviewRequired !== false &&
          !["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition) && (
            <small>人工调整：{ACTION_LABELS[review.action]}</small>
          )}
        {editable && !item.manual && (
          <div className="semantic-review-item-actions">
            <Button
              type="text"
              size="small"
              icon={<PencilSimple size={15} />}
              onClick={() => {
                setDraft({
                  action: review?.action || "change_label",
                  label_code: review?.label_code || item.labelCode || "",
                  note: review?.note || "",
                });
                setEditing((current) => !current);
              }}
            >
              {review ? "调整修改" : "调整"}
            </Button>
            {review && (
              <Button type="text" size="small" onClick={onReset}>
                撤销调整
              </Button>
            )}
          </div>
        )}
      </div>

      <DiagnosticDetails item={item} />

      {editing && (
        <div className="semantic-review-item-editor">
          <label>
            调整方式
            <Select
              aria-label={`调整方式：${item.opinion}`}
              value={draft.action}
              onChange={(action) => setDraft({ ...draft, action })}
              options={Object.entries(ACTION_LABELS).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          </label>
          {draft.action === "change_label" && (
            <label>
              修改为
              <Select
                aria-label={`修改观点标签：${item.opinion}`}
                showSearch
                optionFilterProp="label"
                value={draft.label_code}
                onChange={(label_code) => setDraft({ ...draft, label_code })}
                options={[
                  { value: "", label: "请选择分类标签" },
                  ...labels.map((label) => ({
                    value: label.code,
                    label: `${labelText(label)} · ${label.code}`,
                  })),
                ]}
              />
            </label>
          )}
          <label>
            本项说明（可选）
            <Input
              value={draft.note}
              onChange={(event) => setDraft({ ...draft, note: event.target.value })}
            />
          </label>
          <div>
            <Button onClick={() => setEditing(false)}>取消</Button>
            <Button
              type="primary"
              disabled={draft.action === "change_label" && !draft.label_code}
              onClick={saveDraft}
            >
              保存本项调整
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

/** @param {{record: ReviewRecord, labels: ReviewLabel[], editable: boolean, itemReviews: SemanticItemReview[], addedItems: AddedSemanticItem[], coverageStatus: CoverageStatus, onItemReviews: (value: SemanticItemReview[]) => void, onAddedItems: (value: AddedSemanticItem[]) => void, onCoverageStatus: (value: CoverageStatus) => void}} props */
export function SemanticReviewLedger({
  record,
  labels,
  editable,
  itemReviews,
  addedItems,
  coverageStatus,
  onItemReviews,
  onAddedItems,
  onCoverageStatus,
}) {
  const ledger = useMemo(() => semanticReviewLedger(record), [record]);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({
    evidence_text: "",
    opinion: "",
    label_code: "",
  });
  const reviews = itemReviews ?? [];
  const manualItems = (addedItems ?? []).map(manualItem);
  const items = [...ledger.items.filter((item) => !item.manual), ...manualItems];
  const systemItems = items.filter((item) =>
    ["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition),
  );
  const businessItems = items.filter(
    (item) => !["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition),
  );
  const summary = items.reduce(
    (counts, item) => {
      const review = reviews.find(
        (candidate) => candidate.semantic_item_id === item.id,
      );
      if (item.businessReviewRequired !== false && review?.action === "remove") {
        counts.informational += 1;
        return counts;
      }
      const effective = effectiveReviewItem(item, review);
      const tone = dispositionTone(effective.disposition);
      if (tone === "failure") counts.failures += 1;
      else if (tone === "review") counts.needsReview += 1;
      else if (tone === "informational") counts.informational += 1;
      else counts.mapped += 1;
      return counts;
    },
    { mapped: 0, informational: 0, needsReview: 0, failures: 0 },
  );
  const hasHumanAdjustments =
    reviews.length > 0 ||
    manualItems.length > 0 ||
    coverageStatus !== ledger.coverageStatus;
  const displayedSummary =
    !hasHumanAdjustments && ledger.suppliedSummary ? ledger.suppliedSummary : summary;

  const addItem = () => {
    const next = {
      item_id: nextManualId(addedItems),
      evidence_text: draft.evidence_text.trim(),
      opinion: draft.opinion.trim(),
      label_code: draft.label_code,
      note: "人工补充的遗漏观点",
    };
    onAddedItems([...addedItems, next]);
    setDraft({ evidence_text: "", opinion: "", label_code: "" });
    setAdding(false);
  };

  /** @param {SemanticReviewLedgerItem} item */
  const renderItem = (item) => {
    const review = reviews.find((candidate) => candidate.semantic_item_id === item.id);
    return (
      <ReviewLedgerItem
        key={item.id}
        item={item}
        labels={labels}
        editable={
          editable &&
          !["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition) &&
          item.businessReviewRequired !== false
        }
        review={review}
        onReview={(next) => onItemReviews(upsert(reviews, next))}
        onReset={() =>
          onItemReviews(
            reviews.filter((candidate) => candidate.semantic_item_id !== item.id),
          )
        }
      />
    );
  };

  return (
    <section className="semantic-review-ledger" aria-label="语义核验清单">
      <header>
        <div>
          <b>语义核验清单</b>
          <span>按“原文证据—用户观点—标签或处置”核验，无需逐标签确认。</span>
        </div>
        <div className="semantic-review-summary" aria-label="语义覆盖概览">
          <span>
            <CheckCircle size={15} /> 已归类 {displayedSummary.mapped}
          </span>
          <span>无需归类 {displayedSummary.informational}</span>
          <span className={displayedSummary.needsReview ? "has-review" : ""}>
            待判断 {displayedSummary.needsReview}
          </span>
          <span className={displayedSummary.failures ? "has-failure" : ""}>
            系统异常 {displayedSummary.failures}
          </span>
        </div>
      </header>

      {items.length ? (
        <div className="semantic-review-groups">
          {systemItems.length > 0 && (
            <section className="semantic-review-group is-system" aria-label="系统异常">
              <header>
                <div>
                  <b>系统异常 · {systemItems.length} 项</b>
                  <span>不属于业务标签判断，需由系统重跑或管理员处理。</span>
                </div>
                <span>已锁定编辑</span>
              </header>
              <div className="semantic-review-items">{systemItems.map(renderItem)}</div>
            </section>
          )}
          <section
            className="semantic-review-group is-business"
            aria-label="待人工判断"
          >
            <header>
              <div>
                <b>待人工判断 · {displayedSummary.needsReview} 项</b>
                <span>核对业务观点、证据与标签；已归类项也可按证据修正。</span>
              </div>
            </header>
            {businessItems.length > 0 ? (
              <div className="semantic-review-items">
                {businessItems.map(renderItem)}
              </div>
            ) : (
              <p className="semantic-review-group-empty">当前没有业务语义项。</p>
            )}
          </section>
        </div>
      ) : (
        <div className="semantic-review-empty" role="status">
          <WarningCircle size={18} />
          当前结果没有可核验的观点，请展开完整原文判断是否需要补充。
        </div>
      )}

      {editable && (
        <div className="semantic-review-controls">
          <label>
            观点覆盖判断
            <Select
              aria-label="观点覆盖判断"
              value={coverageStatus}
              onChange={onCoverageStatus}
              options={[
                { value: "complete", label: "已覆盖需要归类的观点" },
                { value: "has_omission", label: "存在遗漏观点" },
              ]}
            />
          </label>
          <Button icon={<Plus size={16} />} onClick={() => setAdding(true)}>
            补充遗漏观点
          </Button>
        </div>
      )}

      {editable && adding && (
        <div className="semantic-review-add-form">
          <b>补充遗漏观点</b>
          <label>
            原文证据
            <Input
              value={draft.evidence_text}
              onChange={(event) =>
                setDraft({ ...draft, evidence_text: event.target.value })
              }
              placeholder="粘贴能够支持该观点的原文片段"
            />
          </label>
          <label>
            用户观点
            <Input
              value={draft.opinion}
              onChange={(event) => setDraft({ ...draft, opinion: event.target.value })}
              placeholder="用一句话概括用户表达的观点"
            />
          </label>
          <label>
            归类标签
            <Select
              aria-label="补充观点的归类标签"
              showSearch
              optionFilterProp="label"
              value={draft.label_code}
              onChange={(label_code) => setDraft({ ...draft, label_code })}
              options={[
                { value: "", label: "请选择分类标签" },
                ...labels.map((label) => ({
                  value: label.code,
                  label: `${labelText(label)} · ${label.code}`,
                })),
              ]}
            />
          </label>
          <div>
            <Button onClick={() => setAdding(false)}>取消</Button>
            <Button
              type="primary"
              disabled={
                !draft.evidence_text.trim() ||
                !draft.opinion.trim() ||
                !draft.label_code
              }
              onClick={addItem}
            >
              添加观点
            </Button>
          </div>
        </div>
      )}

      {editable && addedItems.length > 0 && (
        <div className="semantic-review-added-actions">
          <span>已人工补充 {addedItems.length} 项</span>
          <Button
            type="text"
            size="small"
            icon={<Trash size={15} />}
            onClick={() => onAddedItems(addedItems.slice(0, -1))}
          >
            移除最后一项
          </Button>
        </div>
      )}
    </section>
  );
}

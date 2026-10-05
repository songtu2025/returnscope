import { useState } from "react";
import Button from "antd/es/button";
import { PencilSimple } from "@phosphor-icons/react";
import { labelText } from "../../lib/taxonomyPresentation";
import {
  dispositionTone,
  effectiveReviewItem,
  REVIEW_DISPOSITION_LABELS,
  reviewDiagnosticPresentation,
} from "./semanticReviewPresentation";
import { ACTION_LABELS } from "./semanticReviewDrafts";
import { ReviewItemEditor } from "./SemanticItemEditor";
import { DiagnosticDetails } from "./SemanticReviewDiagnostic";

/** @typedef {import("./semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./semanticLedgerContracts").SemanticItemReview} SemanticItemReview */
/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {SemanticReviewLedgerItem} item @param {ReviewLabel[]} labels */
function labelDisplay(item, labels) {
  const label = labels.find((candidate) => candidate.code === item.labelCode);
  if (label) return labelText(label);
  if (item.labelPath?.length) return item.labelPath.join(" → ");
  return item.labelCode || "未设置标签";
}

/** @param {{item: SemanticReviewLedgerItem, sourceText: string, labels: ReviewLabel[], editable: boolean, review?: SemanticItemReview, onReview: (review: SemanticItemReview) => void, onReset: () => void}} props */
export function ReviewLedgerItem({
  item,
  sourceText,
  labels,
  editable,
  review,
  onReview,
  onReset,
}) {
  const [editing, setEditing] = useState(false);
  const effective = effectiveReviewItem(item, review);
  const removed = review?.action === "remove" && effective !== item;
  const tone = removed ? "informational" : dispositionTone(effective.disposition);
  const statusLabel = reviewItemStatusLabel(removed, effective);
  const diagnostic = reviewDiagnosticPresentation(item, sourceText);

  return (
    <article
      className={`semantic-review-item is-${tone} ${removed ? "is-removed" : ""}`}
    >
      <div className="semantic-review-evidence">
        <span>{item.evidenceSource || "原评论"}</span>
        <blockquote>“{item.evidence}”</blockquote>
      </div>
      <div className="semantic-review-opinion">
        <span>{diagnostic.opinionHeading}</span>
        <p>{item.opinion}</p>
        {item.reason && <small>{item.reason}</small>}
      </div>
      <ReviewItemDecision
        item={item}
        labels={labels}
        editable={editable}
        review={review}
        onReset={onReset}
        setEditing={setEditing}
        effective={effective}
        removed={removed}
        tone={tone}
        statusLabel={statusLabel}
      />

      <DiagnosticDetails item={item} suggestedAction={diagnostic.suggestedAction} />
      {diagnostic.missingEvidence && (
        <p role="note">
          此诊断项缺少可核对的原文证据，请使用“补充遗漏观点”；如需移除错误诊断，选择“删除错误提取”。
        </p>
      )}

      {editing && (
        <ReviewItemEditor
          item={item}
          labels={labels}
          review={review}
          missingEvidence={diagnostic.missingEvidence}
          onSave={(next) => {
            onReview(next);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </article>
  );
}

/** @param {Pick<Parameters<typeof ReviewLedgerItem>[0] & {removed:boolean,tone:string,statusLabel:string,effective:import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem,setEditing:import("react").Dispatch<import("react").SetStateAction<boolean>>}, "item" | "labels" | "editable" | "review" | "onReset" | "setEditing" | "effective" | "removed" | "tone" | "statusLabel">} props */
function ReviewItemDecision({
  item,
  labels,
  editable,
  review,
  onReset,
  setEditing,
  effective,
  removed,
  tone,
  statusLabel,
}) {
  return (
    <div className="semantic-review-decision">
      <span className={`semantic-review-state is-${tone}`}>{statusLabel}</span>
      <ReviewEffectiveDecision
        removed={removed}
        effective={effective}
        labels={labels}
      />
      {review &&
        item.businessReviewRequired !== false &&
        dispositionTone(item.disposition) !== "failure" && (
          <small>人工调整：{ACTION_LABELS[review.action]}</small>
        )}
      {editable && !item.manual && (
        <ReviewItemActions review={review} onReset={onReset} setEditing={setEditing} />
      )}
    </div>
  );
}
/** @param {Pick<Parameters<typeof ReviewItemDecision>[0], "review" | "onReset" | "setEditing">} props */
function ReviewItemActions({ review, onReset, setEditing }) {
  return (
    <div className="semantic-review-item-actions">
      <Button
        type="text"
        size="small"
        icon={<PencilSimple size={15} />}
        onClick={() => {
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
  );
}

/** @param {boolean} removed @param {SemanticReviewLedgerItem} effective */
function reviewItemStatusLabel(removed, effective) {
  const statusLabel = removed
    ? "已标记删除"
    : REVIEW_DISPOSITION_LABELS[effective.disposition] || effective.disposition;
  return statusLabel;
}
/** @param {Pick<Parameters<typeof ReviewItemDecision>[0], "removed" | "effective" | "labels">} props */
function ReviewEffectiveDecision({ removed, effective, labels }) {
  return (
    <>
      {" "}
      {!removed && effective.disposition === "MAPPED" && (
        <b>{labelDisplay(effective, labels)}</b>
      )}
      {!removed && effective.disposition !== "MAPPED" && effective.reason && (
        <small>{effective.reason}</small>
      )}
    </>
  );
}

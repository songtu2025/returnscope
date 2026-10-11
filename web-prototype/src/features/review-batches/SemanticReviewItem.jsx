import { labelText } from "../../lib/taxonomyPresentation";
import {
  dispositionTone,
  effectiveReviewItem,
  REVIEW_DISPOSITION_LABELS,
  reviewDiagnosticPresentation,
} from "./semanticReviewPresentation";
import { ACTION_LABELS } from "./semanticReviewDrafts";
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

/** @param {{item: SemanticReviewLedgerItem, sourceText: string, labels: ReviewLabel[], review?: SemanticItemReview}} props */
export function ReviewLedgerItem({ item, sourceText, labels, review }) {
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
        review={review}
        effective={effective}
        removed={removed}
        tone={tone}
        statusLabel={statusLabel}
      />

      <DiagnosticDetails item={item} suggestedAction={diagnostic.suggestedAction} />
      {diagnostic.missingEvidence && (
        <p role="note">当时记录的诊断项缺少可核对的原文证据。</p>
      )}
    </article>
  );
}

/** @param {Pick<Parameters<typeof ReviewLedgerItem>[0] & {removed:boolean,tone:string,statusLabel:string,effective:import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem}, "item" | "labels" | "review" | "effective" | "removed" | "tone" | "statusLabel">} props */
function ReviewItemDecision({
  item,
  labels,
  review,
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

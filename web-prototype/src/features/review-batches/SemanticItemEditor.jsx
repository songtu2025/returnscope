import { useState } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { labelText } from "../../lib/taxonomyPresentation";
import { selectedSentiment, ACTION_LABELS } from "./semanticReviewDrafts";
import { SentimentField } from "./SemanticSentimentField";

/** @typedef {import("./semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./semanticLedgerContracts").SemanticItemReview} SemanticItemReview */
/** @typedef {import("./semanticLedgerContracts").SemanticReviewAction} SemanticReviewAction */
/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {{item: SemanticReviewLedgerItem, labels: ReviewLabel[], review?: SemanticItemReview, missingEvidence: boolean, onSave: (review: SemanticItemReview) => void, onCancel: () => void}} props */
export function ReviewItemEditor({
  item,
  labels,
  review,
  missingEvidence,
  onSave,
  onCancel,
}) {
  const [draft, setDraft] = useState(() => ({
    action: /** @type {SemanticReviewAction} */ (review?.action || "change_label"),
    label_code: review?.label_code || item.labelCode || "",
    note: review?.note || "",
    sentiment: review?.sentiment || "",
  }));
  const saveDraft = () => {
    onSave({
      semantic_item_id: item.id,
      action: draft.action,
      label_code: draft.action === "change_label" ? draft.label_code : null,
      note: draft.note.trim() || null,
      ...(draft.action === "change_label" && !item.sentiment
        ? {
            sentiment: selectedSentiment(draft.label_code, labels, draft.sentiment),
          }
        : {}),
    });
  };

  return (
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
            onChange={(label_code) => setDraft({ ...draft, label_code, sentiment: "" })}
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
      {draft.action === "change_label" && (
        <SentimentField
          code={draft.label_code}
          labels={labels}
          value={draft.sentiment}
          known={item.sentiment}
          name={`观点评价方向：${item.opinion}`}
          onChange={(sentiment) => setDraft({ ...draft, sentiment })}
        />
      )}
      <label>
        本项说明（可选）
        <Input
          value={draft.note}
          onChange={(event) => setDraft({ ...draft, note: event.target.value })}
        />
      </label>
      <div>
        <Button onClick={onCancel}>取消</Button>
        <Button
          type="primary"
          disabled={
            (missingEvidence && draft.action !== "remove") ||
            (draft.action === "change_label" &&
              (!draft.label_code ||
                !selectedSentiment(
                  draft.label_code,
                  labels,
                  item.sentiment || draft.sentiment,
                )))
          }
          onClick={saveDraft}
        >
          保存本项调整
        </Button>
      </div>
    </div>
  );
}

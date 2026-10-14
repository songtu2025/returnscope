import { useId } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { labelText } from "../../lib/taxonomyPresentation";
import { semanticItemErrors } from "./manualSemanticValidation";
import { SentimentField } from "../review-batches/SemanticSentimentField";

/** @typedef {import("../review-batches/semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./manualSemanticValidation").Draft} Draft */
/** @param {{items: Draft[], labels: ReviewLabel[], disabled: boolean, loading: boolean, onEdit: (index: number, change: Partial<Draft>) => void, onRemove: (index: number) => void}} props */
export function ManualSemanticFields({
  items,
  labels,
  disabled,
  loading,
  onEdit,
  onRemove,
}) {
  const id = useId();
  return items.map((item, index) => {
    const errors = loading ? null : semanticItemErrors(item, labels);
    const prefix = `${id}-${item.item_id}`;
    const error = (/** @type {keyof ReturnType<typeof semanticItemErrors>} */ field) =>
      errors?.[field] ? (
        <span id={`${prefix}-${field}-error`} role="alert">
          {errors[field]}
        </span>
      ) : null;
    const attributes = (
      /** @type {keyof ReturnType<typeof semanticItemErrors>} */ field,
    ) => ({
      "aria-invalid": Boolean(errors?.[field]),
      "aria-describedby": errors?.[field] ? `${prefix}-${field}-error` : undefined,
    });
    return (
      <div className="manual-semantic-item" key={item.item_id}>
        <div className="manual-semantic-item-heading">
          <b>观点 {index + 1}</b>
          <Button disabled={disabled} onClick={() => onRemove(index)}>
            删除观点 {index + 1}
          </Button>
        </div>
        <label>
          原文证据
          <Input
            {...attributes("evidence_text")}
            aria-label={`观点 ${index + 1} 原文证据`}
            value={item.evidence_text}
            onChange={(event) => onEdit(index, { evidence_text: event.target.value })}
          />
          {error("evidence_text")}
        </label>
        <label>
          用户观点
          <Input
            {...attributes("opinion")}
            aria-label={`观点 ${index + 1} 用户观点`}
            value={item.opinion}
            onChange={(event) => onEdit(index, { opinion: event.target.value })}
          />
          {error("opinion")}
        </label>
        <label>
          归类标签
          <Select
            {...attributes("label_code")}
            aria-label={`观点 ${index + 1} 归类标签`}
            disabled={disabled}
            showSearch
            optionFilterProp="label"
            value={item.label_code || undefined}
            placeholder="请选择分类标签"
            onChange={(label_code) => onEdit(index, { label_code, sentiment: "" })}
            options={labels.map((label) => ({
              value: label.code,
              label: labelText(label),
            }))}
            getPopupContainer={(trigger) => trigger.parentElement}
          />
          {error("label_code")}
        </label>
        <div
          role="group"
          aria-label={`观点 ${index + 1} 评价方向校验`}
          {...attributes("sentiment")}
        >
          <SentimentField
            code={item.label_code}
            labels={labels}
            value={item.sentiment}
            disabled={disabled}
            name={`观点 ${index + 1} 评价方向`}
            onChange={(sentiment) => onEdit(index, { sentiment })}
          />
          {error("sentiment")}
        </div>
      </div>
    );
  });
}

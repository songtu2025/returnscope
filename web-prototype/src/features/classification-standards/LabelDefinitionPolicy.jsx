import {
  CLASSIFICATION_LABEL_SENTIMENTS as SENTIMENTS,
  CLASSIFICATION_LABEL_SENTIMENT_VALUES as SENTIMENT_VALUES,
} from "./classificationLabelSentiments";
/** @typedef {import("./ClassificationLabelDefinition").ClassificationLabelDefinitionProps} DefinitionProps */
/** @typedef {Pick<DefinitionProps, "label" | "entry" | "labelFieldRefs" | "updateLabel" | "content" | "onChange">} PolicyProps */
/** @type {{field: "required_review_labels" | "neutral_reason_labels", title: string}[]} */
const REVIEW_RULE_OPTIONS = [
  { field: "required_review_labels", title: "使用此标签时必须人工复核" },
  { field: "neutral_reason_labels", title: "中性反馈可作为退货原因" },
];

/** @param {Pick<PolicyProps, "label" | "entry" | "labelFieldRefs" | "updateLabel">} props */
function LabelSentimentOptions({ label, entry, labelFieldRefs, updateLabel }) {
  return (
    <fieldset className="wide-field label-sentiment-options">
      <legend>支持的评价方向</legend>
      {SENTIMENT_VALUES.map((value) => (
        <label key={value}>
          <input
            ref={(node) => {
              if (value === "NEGATIVE")
                labelFieldRefs.current.set(`${entry.index}.allowed_sentiments`, node);
            }}
            type="checkbox"
            checked={label.allowed_sentiments.includes(value)}
            onChange={(event) =>
              updateLabel({
                allowed_sentiments: event.target.checked
                  ? [...label.allowed_sentiments, value]
                  : label.allowed_sentiments.filter((item) => item !== value),
              })
            }
          />
          {SENTIMENTS[value]}
        </label>
      ))}
    </fieldset>
  );
}
/** @param {Pick<PolicyProps, "label" | "content" | "onChange">} props */
function LabelReviewOptions({ label, content, onChange }) {
  return (
    <fieldset className="wide-field label-sentiment-options">
      <legend>统计与复核</legend>
      {REVIEW_RULE_OPTIONS.filter(
        ({ field }) =>
          field !== "neutral_reason_labels" ||
          label.allowed_sentiments.includes("NEUTRAL"),
      ).map(({ field, title }) => (
        <label key={field}>
          <input
            type="checkbox"
            checked={(content.validation_rules?.[field] ?? []).includes(label.code)}
            onChange={(event) => {
              const values = content.validation_rules?.[field] ?? [];
              onChange({
                ...content,
                validation_rules: {
                  ...content.validation_rules,
                  [field]: event.target.checked
                    ? [...new Set([...values, label.code])]
                    : values.filter((code) => code !== label.code),
                },
              });
            }}
          />
          {title}
        </label>
      ))}
    </fieldset>
  );
}
/** @param {PolicyProps} props */
export function LabelDefinitionPolicy({
  label,
  entry,
  labelFieldRefs,
  updateLabel,
  content,
  onChange,
}) {
  return (
    <>
      <LabelSentimentOptions
        label={label}
        entry={entry}
        labelFieldRefs={labelFieldRefs}
        updateLabel={updateLabel}
      />
      <LabelReviewOptions label={label} content={content} onChange={onChange} />
    </>
  );
}

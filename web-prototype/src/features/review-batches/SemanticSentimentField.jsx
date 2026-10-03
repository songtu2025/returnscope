import Select from "antd/es/select";
import { selectedSentiment, SENTIMENT_LABELS } from "./semanticReviewDrafts";

/** @typedef {import("./semanticLedgerContracts").ReviewLabel} ReviewLabel */

/** @param {{code: string, labels: ReviewLabel[], value: string, onChange: (value: string) => void, name: string, known?: string}} props */
export function SentimentField({ code, labels, value, onChange, name, known }) {
  if (!code) return null;
  const allowed = labels.find((label) => label.code === code)?.allowed_sentiments ?? [];
  const selected = selectedSentiment(code, labels, known || value);
  return (
    <label>
      评价方向
      {known || allowed.length === 1 ? (
        <span>{SENTIMENT_LABELS[selected]}（沿用原结果或标签规则）</span>
      ) : (
        <Select
          aria-label={name}
          value={selected || undefined}
          onChange={onChange}
          placeholder="请选择评价方向"
          options={allowed.map((sentiment) => ({
            value: sentiment,
            label: SENTIMENT_LABELS[sentiment],
          }))}
        />
      )}
    </label>
  );
}

import { RESULT_STATE_LABELS } from "../classification-results/resultStatePolicy";

const STATUS_OPTIONS = [
  { value: "ready", label: RESULT_STATE_LABELS.ready },
  { value: "review_required", label: RESULT_STATE_LABELS.needs_review },
  { value: "unusable", label: RESULT_STATE_LABELS.unusable },
  { value: "excluded", label: "已忽略" },
];

/** @param {{statuses: string[], onChange: (statuses: string[]) => void, disabled?: boolean}} props */
export function DashboardQualityScope({ statuses, onChange, disabled = false }) {
  return (
    <fieldset className="dashboard-quality-scope" disabled={disabled}>
      <legend>统计记录范围</legend>
      <div className="dashboard-quality-options">
        {STATUS_OPTIONS.map(({ value, label }) => (
          <label key={value}>
            <input
              type="checkbox"
              checked={statuses.includes(value)}
              disabled={statuses.includes(value) && statuses.length === 1}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...statuses, value]
                    : statuses.filter((status) => status !== value),
                )
              }
            />
            {label}
          </label>
        ))}
      </div>
      <small>
        默认仅可用记录。其他记录由你决定是否纳入；没有分类结论的记录不会补造语义标签。
      </small>
    </fieldset>
  );
}

import { SEMANTIC_STATUS_LABELS } from "./semanticStatusPresentation";
import { RESULT_STATE_LABELS } from "./resultStatePolicy";

/** @param {Pick<import("./classificationResultDetailContracts").ResultDetailContext, "route" | "updateRoute">} props */
export function ResultRecordFilters({ route, updateRoute }) {
  const filtered = Boolean(route.recordQualityStatus || route.commentStatus);
  return (
    <div className="result-record-filters" role="group" aria-label="结果筛选">
      <label>
        结果状态
        <select
          value={route.recordQualityStatus}
          onChange={(event) =>
            updateRoute({ recordQualityStatus: event.target.value, recordPage: 1 })
          }
        >
          <option value="">全部状态</option>
          <option value="ready">{RESULT_STATE_LABELS.ready}</option>
          <option value="review_required">{RESULT_STATE_LABELS.needs_review}</option>
          <option value="unusable">{RESULT_STATE_LABELS.unusable}</option>
          <option value="excluded">已忽略</option>
        </select>
      </label>
      <label>
        语义类型
        <select
          value={route.commentStatus}
          onChange={(event) =>
            updateRoute({ commentStatus: event.target.value, recordPage: 1 })
          }
        >
          <option value="">全部类型</option>
          {Object.entries(SEMANTIC_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <button
        className="text-button"
        disabled={!filtered}
        onClick={() =>
          updateRoute({ recordQualityStatus: "", commentStatus: "", recordPage: 1 })
        }
      >
        清除结果筛选
      </button>
    </div>
  );
}

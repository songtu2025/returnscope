import Button from "antd/es/button";
import Select from "antd/es/select";
import { useId } from "react";
import { SEMANTIC_STATUS_LABELS } from "./semanticStatusPresentation";
import { RESULT_STATE_LABELS } from "./resultStatePolicy";

/** @param {Pick<import("./classificationResultDetailContracts").ResultDetailContext, "route" | "updateRoute"> & {children: import("react").ReactNode}} props */
export function ResultRecordFilters({ route, updateRoute, children }) {
  const id = useId();
  const filtered = Boolean(
    route.recordQualityStatus || route.commentStatus || route.systemRerunRequired,
  );
  return (
    <div className="result-record-filters" role="group" aria-label="结果筛选">
      <div className="result-record-field">
        <label htmlFor={`${id}-quality`}>结果状态</label>
        <Select
          id={`${id}-quality`}
          aria-label="结果状态"
          virtual={false}
          value={route.recordQualityStatus}
          onChange={(recordQualityStatus) =>
            updateRoute({ recordQualityStatus, recordPage: 1 })
          }
          options={[
            { value: "", label: "全部状态" },
            { value: "ready", label: RESULT_STATE_LABELS.ready },
            { value: "review_required", label: RESULT_STATE_LABELS.needs_review },
            { value: "unusable", label: RESULT_STATE_LABELS.unusable },
            { value: "excluded", label: "已忽略" },
          ]}
        />
      </div>
      <div className="result-record-field">
        <label htmlFor={`${id}-semantic`}>语义类型</label>
        <Select
          id={`${id}-semantic`}
          aria-label="语义类型"
          virtual={false}
          value={route.commentStatus}
          onChange={(commentStatus) => updateRoute({ commentStatus, recordPage: 1 })}
          options={[
            { value: "", label: "全部类型" },
            ...Object.entries(SEMANTIC_STATUS_LABELS).map(([value, label]) => ({
              value,
              label,
            })),
          ]}
        />
      </div>
      <div className="result-record-field">
        <label htmlFor={`${id}-rerun`}>重跑标记</label>
        <Select
          id={`${id}-rerun`}
          aria-label="重跑标记"
          virtual={false}
          value={route.systemRerunRequired}
          onChange={(systemRerunRequired) =>
            updateRoute({ systemRerunRequired, recordPage: 1 })
          }
          options={[
            { value: "", label: "全部" },
            { value: "true", label: "需重跑" },
            { value: "false", label: "无需重跑" },
          ]}
        />
      </div>
      {children}
      <Button
        disabled={!filtered}
        onClick={() =>
          updateRoute({
            recordQualityStatus: "",
            commentStatus: "",
            systemRerunRequired: "",
            recordPage: 1,
          })
        }
      >
        清除结果筛选
      </Button>
    </div>
  );
}

import { CheckCircle, Clock, Pulse, WarningCircle } from "@phosphor-icons/react";
import { EFFORT_LABELS } from "../../constants";
import { classNames } from "../../lib/presentation";

/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationItem} ValidationItemData */

/** @param {{validationRun: ValidationRun, validationElapsed: number, validationActive: boolean}} props */
export function ModelValidationProgress({
  validationRun,
  validationElapsed,
  validationActive,
}) {
  return (
    <>
      <div className="validation-progress-heading">
        <b>
          验证进度 {validationRun.completed_count} / {validationRun.total_count}
        </b>
        {validationActive && <span>离开页面后仍会继续验证</span>}
      </div>
      <div className="validation-progress-track">
        <span
          style={{
            width: `${
              validationRun.total_count
                ? (validationRun.completed_count / validationRun.total_count) * 100
                : 0
            }%`,
          }}
        />
      </div>
      <div className="validation-item-list">
        {(validationRun.items ?? []).map((item, index) => (
          <ValidationItem
            key={`${item.model_id}-${index}`}
            item={item}
            validationRun={validationRun}
            validationElapsed={validationElapsed}
          />
        ))}
      </div>
    </>
  );
}

/** @param {{item: ValidationItemData, validationRun: ValidationRun, validationElapsed: number}} props */
function ValidationItem({ item, validationRun, validationElapsed }) {
  const itemStarted = new Date(item.started_at ?? "").getTime();
  const runStarted = new Date(
    validationRun.started_at ?? validationRun.created_at,
  ).getTime();
  const itemElapsed =
    Number.isNaN(itemStarted) || Number.isNaN(runStarted)
      ? validationElapsed
      : Math.max(0, validationElapsed - (itemStarted - runStarted) / 1000);
  return (
    <div className={classNames("validation-item", item.status)}>
      <ValidationStatusIcon status={item.status} />
      <div className="validation-item-copy">
        <div>
          <b>{item.display_name}</b>
          <code>{item.model_key}</code>
          <span>{item.role}</span>
        </div>
        <p>{item.message}</p>
        {item.suggestion && <small>处理建议：{item.suggestion}</small>}
      </div>
      <div className="validation-item-meta">
        <span>
          推理强度：
          {/** @type {Record<string, string>} */ (EFFORT_LABELS)[item.effort]}
        </span>
        {item.status === "running" && <b>{itemElapsed.toFixed(1)} 秒</b>}
        {item.duration_ms !== null && <b>{(item.duration_ms / 1000).toFixed(2)} 秒</b>}
        {item.http_status && <span>HTTP {item.http_status}</span>}
      </div>
    </div>
  );
}

/** @param {{status: string}} props */
function ValidationStatusIcon({ status }) {
  if (status === "passed") return <CheckCircle size={18} />;
  if (status === "failed") return <WarningCircle size={18} />;
  if (status === "running") return <Pulse className="validation-pulse" size={18} />;
  return <Clock size={18} />;
}

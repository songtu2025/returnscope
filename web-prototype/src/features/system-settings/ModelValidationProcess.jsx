import { WarningCircle } from "@phosphor-icons/react";
import { classNames, formatTime } from "../../lib/presentation";
import { ModelValidationProgress } from "./ModelValidationProgress";

/** @typedef {import("../../shared/api/systemSettingsContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationEvent} ValidationEvent */

/** @type {Record<string, string>} */
const VALIDATION_STATUS_LABELS = {
  queued: "等待开始",
  running: "验证中",
  passed: "验证通过",
  failed: "验证失败",
  skipped: "已跳过",
  pending: "等待验证",
};

/**
 * @typedef {{
 *   busy: string,
 *   onClose: () => void,
 *   onPublish: () => void,
 *   selectedVersion: ConfigVersion | null,
 *   selectedVersionIsActive: boolean,
 *   validationActive: boolean,
 *   validationElapsed: number,
 *   validationEvents: ValidationEvent[],
 *   validationRun: ValidationRun | null,
 * }} ValidationProcessProps
 */
/** @param {ValidationProcessProps} props */
export function ValidationProcess(props) {
  const { validationRun, validationElapsed, validationEvents, selectedVersion } = props;
  if (!validationRun) return null;
  return (
    <section
      id="validation-process"
      className={classNames("validation-process", validationRun.status)}
    >
      <ValidationProcessHeader {...props} validationRun={validationRun} />
      <ValidationContext
        validationRun={validationRun}
        selectedVersion={selectedVersion}
      />
      <ModelValidationProgress
        validationRun={validationRun}
        validationElapsed={validationElapsed}
        validationActive={props.validationActive}
      />
      <ValidationOutcome
        validationRun={validationRun}
        validationEvents={validationEvents}
      />
    </section>
  );
}

/** @param {ValidationProcessProps & {validationRun: ValidationRun}} props */
function ValidationProcessHeader(props) {
  return (
    <header>
      <div>
        <span className="validation-process-kicker">
          {props.validationRun.kind === "config" ? "模型流水线验证" : "单模型验证"}
        </span>
        <h4>
          {VALIDATION_STATUS_LABELS[props.validationRun.status] ??
            props.validationRun.status}
          {props.validationActive && (
            <small>{props.validationElapsed.toFixed(1)} 秒</small>
          )}
        </h4>
      </div>
      {!props.validationActive && (
        <div className="validation-process-actions">
          {props.validationRun.kind === "config" &&
            props.validationRun.status === "passed" &&
            !props.selectedVersionIsActive && (
              <button
                className="primary-button"
                type="button"
                onClick={props.onPublish}
                disabled={Boolean(props.busy)}
              >
                发布新版本
              </button>
            )}
          <button type="button" onClick={props.onClose} disabled={Boolean(props.busy)}>
            关闭
          </button>
        </div>
      )}
    </header>
  );
}

/** @param {Pick<ValidationProcessProps, "validationRun" | "selectedVersion"> & {validationRun: ValidationRun}} props */
function ValidationContext({ validationRun, selectedVersion }) {
  return (
    <>
      <div className="validation-context-grid">
        <div>
          <span>验证地址</span>
          <code>{validationRun.endpoint}</code>
        </div>
        <div>
          <span>请求超时</span>
          <b>{validationRun.timeout_seconds} 秒</b>
        </div>
        <div>
          <span>发起人</span>
          <b>{validationRun.creator_name}</b>
        </div>
        <div>
          <span>验证范围</span>
          <b>配置 #{selectedVersion?.version} · 连接及策略使用的全部模型</b>
        </div>
      </div>
      <p className="validation-cost-note">
        <WarningCircle size={16} />
        本次会发送真实模型请求，可能产生少量模型费用；API 密钥和完整响应不会展示。
      </p>
    </>
  );
}

/** @param {Pick<ValidationProcessProps, "validationRun" | "validationEvents"> & {validationRun: ValidationRun}} props */
function ValidationOutcome({ validationRun, validationEvents }) {
  return (
    <>
      {validationEvents.length > 0 && (
        <div className="validation-event-list">
          <b>实时过程</b>
          {validationEvents.slice(-8).map((event) => (
            <div key={event.id}>
              <span />
              <time>{formatTime(event.created_at)}</time>
              <p>{event.message}</p>
            </div>
          ))}
        </div>
      )}
      {validationRun.status === "failed" && (
        <div className="validation-failure-summary">
          <b>{validationRun.error_message}</b>
          <p>{validationRun.suggestion}</p>
        </div>
      )}
    </>
  );
}

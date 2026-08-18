import { CheckCircle, Clock, Plus, Pulse, WarningCircle } from "@phosphor-icons/react";
import { CardHeading } from "../../components/SharedUi";
import { EFFORT_LABELS, MODEL_STATUS_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";

const VALIDATION_STATUS_LABELS = {
  queued: "等待开始",
  running: "验证中",
  passed: "验证通过",
  failed: "验证失败",
  skipped: "已跳过",
  pending: "等待验证",
};

function ValidationStatusIcon({ status }) {
  if (status === "passed") return <CheckCircle size={18} />;
  if (status === "failed") return <WarningCircle size={18} />;
  if (status === "running") return <Pulse className="validation-pulse" size={18} />;
  return <Clock size={18} />;
}

function ValidationProcess({
  busy,
  onClose,
  onPublish,
  selectedVersion,
  selectedVersionIsActive,
  validationActive,
  validationElapsed,
  validationEvents,
  validationRun,
}) {
  if (!validationRun) return null;

  return (
    <section
      id="validation-process"
      className={classNames("validation-process", validationRun.status)}
    >
      <header>
        <div>
          <span className="validation-process-kicker">
            {validationRun.kind === "config" ? "模型流水线验证" : "单模型验证"}
          </span>
          <h4>
            {VALIDATION_STATUS_LABELS[validationRun.status] ?? validationRun.status}
            {validationActive && <small>{validationElapsed.toFixed(1)} 秒</small>}
          </h4>
        </div>
        {!validationActive && (
          <div className="validation-process-actions">
            {validationRun.kind === "config" &&
              validationRun.status === "passed" &&
              !selectedVersionIsActive && (
                <button
                  className="primary-button"
                  type="button"
                  onClick={onPublish}
                  disabled={Boolean(busy)}
                >
                  发布新版本
                </button>
              )}
            <button type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        )}
      </header>
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
        {(validationRun.items ?? []).map((item, index) => {
          const itemStarted = new Date(item.started_at).getTime();
          const runStarted = new Date(
            validationRun.started_at ?? validationRun.created_at,
          ).getTime();
          const itemElapsed =
            Number.isNaN(itemStarted) || Number.isNaN(runStarted)
              ? validationElapsed
              : Math.max(0, validationElapsed - (itemStarted - runStarted) / 1000);
          return (
            <div
              className={classNames("validation-item", item.status)}
              key={`${item.model_id}-${index}`}
            >
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
                <span>推理强度：{EFFORT_LABELS[item.effort]}</span>
                {item.status === "running" && <b>{itemElapsed.toFixed(1)} 秒</b>}
                {item.duration_ms !== null && (
                  <b>{(item.duration_ms / 1000).toFixed(2)} 秒</b>
                )}
                {item.http_status && <span>HTTP {item.http_status}</span>}
              </div>
            </div>
          );
        })}
      </div>
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
    </section>
  );
}

export function ModelCatalogSection({
  busy,
  catalogModels,
  focusModelId,
  focusedModelRef,
  onCloseValidation,
  onOpenModelEditor,
  onPublish,
  onToggleModel,
  onValidateModel,
  selectedConnection,
  selectedVersion,
  selectedVersionIsActive,
  validationActive,
  validationElapsed,
  validationEvents,
  validationRun,
}) {
  return (
    <div className="config-section" id="available-models">
      <CardHeading
        title="可用模型"
        note={
          selectedConnection
            ? "目录来自当前接入的 /models；仅已启用且验证通过的模型可供选择。"
            : "请添加接入方提供的模型 ID；保存后可同步真实目录并验证。"
        }
        action={
          <button className="secondary-button" onClick={() => onOpenModelEditor()}>
            <Plus size={16} />
            添加模型
          </button>
        }
      />
      <div className="model-catalog-list">
        {catalogModels.map((model) => (
          <div
            ref={String(model.id) === String(focusModelId) ? focusedModelRef : null}
            className={classNames(
              "model-catalog-row",
              !model.active && "inactive",
              String(model.id) === String(focusModelId) && "is-targeted",
            )}
            key={model.id}
          >
            <div className="model-catalog-name">
              <b>{model.display_name}</b>
              <code>{model.model_key}</code>
              {model.updater_name && (
                <small>
                  最近修改：{model.updater_name} · {formatTime(model.updated_at)}
                </small>
              )}
            </div>
            <div className="model-effort-tags">
              {model.supported_efforts.map((effort) => (
                <span key={effort}>{EFFORT_LABELS[effort]}</span>
              ))}
            </div>
            <span
              className={classNames("model-validation-badge", model.validation_status)}
              title={model.validation_message || ""}
            >
              {model.active
                ? (MODEL_STATUS_LABELS[model.validation_status] ?? "待验证")
                : "已停用"}
            </span>
            <div className="model-catalog-actions">
              {selectedConnection && model.active && (
                <button
                  type="button"
                  onClick={() => onValidateModel(model)}
                  disabled={Boolean(busy) || validationActive}
                >
                  {validationActive && validationRun?.target_id === model.id
                    ? "验证中…"
                    : busy === "validation-start"
                      ? "启动中…"
                      : "验证"}
                </button>
              )}
              <button
                type="button"
                onClick={() => onOpenModelEditor(model)}
                disabled={Boolean(busy) || validationActive}
              >
                编辑
              </button>
              <button
                type="button"
                onClick={() => onToggleModel(model)}
                disabled={Boolean(busy) || validationActive}
              >
                {model.active ? "停用" : "启用"}
              </button>
            </div>
          </div>
        ))}
      </div>
      <ValidationProcess
        busy={busy}
        onClose={onCloseValidation}
        onPublish={onPublish}
        selectedVersion={selectedVersion}
        selectedVersionIsActive={selectedVersionIsActive}
        validationActive={validationActive}
        validationElapsed={validationElapsed}
        validationEvents={validationEvents}
        validationRun={validationRun}
      />
    </div>
  );
}

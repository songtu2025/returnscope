import {
  ArrowRight,
  CaretDown,
  CheckCircle,
  Plus,
  Power,
  WarningCircle,
} from "@phosphor-icons/react";
import { EFFORT_LABELS, MODEL_STATUS_LABELS } from "../../constants";
import { classNames } from "../../lib/presentation";

export function ModelServiceSummary({
  connections,
  selectedConnectionId,
  selectedConnection,
  activeVersion,
  availableModelCount,
  busy,
  validationActive,
  draftVersion,
  discardConfirmation,
  visibleCatalogModels,
  onSelectConnection,
  onStartValidation,
  onOpenNewConnection,
  onEditConnection,
  onEditLimits,
  onOpenVersions,
  onCancelDiscard,
  onDiscardDraft,
  onPublishDraft,
  onContinueDraft,
  onConfirmDiscard,
  onDiscoverModels,
  onOpenModelCatalog,
  onValidateCatalogModel,
}) {
  return (
    <div className="model-service-summary">
      {connections.length > 1 && (
        <label className="model-service-selector">
          模型服务
          <select
            value={selectedConnectionId ?? ""}
            onChange={(event) => onSelectConnection(event.target.value)}
          >
            {connections.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <section className="content-card model-service-runtime">
        <div
          className={classNames(
            "model-service-runtime-icon",
            activeVersion?.validation_status === "validated" && "online",
          )}
        >
          {activeVersion?.validation_status === "validated" ? (
            <CheckCircle size={36} weight="duotone" />
          ) : (
            <WarningCircle size={36} weight="duotone" />
          )}
        </div>
        <div className="model-service-runtime-main">
          <span className="asset-type">当前接入</span>
          <div className="model-service-runtime-title">
            <h2>{selectedConnection?.name ?? "尚未创建模型服务"}</h2>
            <span
              className={classNames(
                "model-service-status",
                activeVersion?.validation_status,
              )}
            >
              {activeVersion?.validation_status === "validated"
                ? "运行正常"
                : activeVersion
                  ? "等待验证"
                  : "尚未发布"}
            </span>
          </div>
          <div className="model-service-runtime-meta">
            <span>
              服务地址 <b>{activeVersion?.base_url ?? "—"}</b>
            </span>
            <span>运行版本 {activeVersion ? `#${activeVersion.version}` : "—"}</span>
            <span>{availableModelCount} 个可用模型</span>
          </div>
        </div>
        <div className="model-service-runtime-actions">
          {activeVersion ? (
            <button
              className="primary-button"
              onClick={() => onStartValidation(activeVersion)}
              disabled={Boolean(busy) || validationActive}
            >
              <Power size={17} />
              {validationActive ? "验证中…" : "验证服务"}
            </button>
          ) : (
            <button className="primary-button" onClick={onOpenNewConnection}>
              <Plus size={18} />
              新增模型服务
            </button>
          )}
          {selectedConnection && (
            <button className="text-button" onClick={onEditConnection}>
              编辑连接
            </button>
          )}
          {selectedConnection && (
            <details className="model-service-more">
              <summary role="button" aria-haspopup="menu">
                更多 <CaretDown size={15} />
              </summary>
              <div
                className="model-service-more-menu"
                role="menu"
                aria-label="更多模型服务操作"
              >
                <button type="button" role="menuitem" onClick={onEditLimits}>
                  请求限制
                </button>
                <button type="button" role="menuitem" onClick={onOpenVersions}>
                  配置版本
                </button>
                {activeVersion && (
                  <button type="button" role="menuitem" onClick={onOpenNewConnection}>
                    新增模型服务
                  </button>
                )}
              </div>
            </details>
          )}
        </div>
      </section>
      {draftVersion && (
        <section className="model-service-draft-strip">
          <div className="model-service-draft-copy">
            <WarningCircle size={22} weight="duotone" />
            <p>
              <b>
                草稿 #{draftVersion.version} ·{" "}
                {draftVersion.validation_status === "validated"
                  ? "可发布"
                  : draftVersion.validation_status === "failed"
                    ? "验证失败"
                    : "待验证"}
              </b>
              <span>
                {draftVersion.change_note || "未填写变更说明"}；当前运行
                {activeVersion ? ` #${activeVersion.version}` : ""} 不受影响
              </span>
            </p>
          </div>
          {discardConfirmation ? (
            <div className="model-service-discard-confirmation">
              <span>放弃后不可恢复</span>
              <button
                className="text-button"
                onClick={onCancelDiscard}
                disabled={busy === "discard-draft"}
              >
                取消
              </button>
              <button
                className="danger-button"
                onClick={onDiscardDraft}
                disabled={busy === "discard-draft"}
              >
                {busy === "discard-draft" ? "放弃中…" : "确认放弃"}
              </button>
            </div>
          ) : (
            <div className="model-service-draft-actions">
              <button
                className="primary-button"
                onClick={
                  draftVersion.validation_status === "validated"
                    ? onPublishDraft
                    : onContinueDraft
                }
                disabled={Boolean(busy) || validationActive}
              >
                {draftVersion.validation_status === "validated"
                  ? "发布版本"
                  : "继续处理"}
              </button>
              <button
                className="text-button"
                onClick={onConfirmDiscard}
                disabled={Boolean(busy) || validationActive}
              >
                放弃草稿
              </button>
            </div>
          )}
        </section>
      )}
      <section className="model-service-catalog">
        <header>
          <div>
            <span className="asset-type">模型目录</span>
            <h3>可用模型</h3>
            <p>模型 ID 来自当前接入的 /models；仅已启用且验证通过的模型可被使用。</p>
          </div>
          <div className="model-service-catalog-actions">
            <button
              className="text-button"
              onClick={onDiscoverModels}
              disabled={!selectedConnection || Boolean(busy) || validationActive}
            >
              {busy === "model-discover" ? "读取中…" : "同步目录"}
            </button>
            <button
              className="text-button"
              onClick={onOpenModelCatalog}
              disabled={!selectedConnection}
            >
              管理目录 <ArrowRight size={15} />
            </button>
          </div>
        </header>
        <div className="model-service-catalog-table" role="table">
          <div className="model-service-catalog-head" role="row">
            <span>模型 ID</span>
            <span>推理强度</span>
            <span>验证状态</span>
            <span>操作</span>
          </div>
          {selectedConnection ? (
            visibleCatalogModels.map((model) => (
              <div className="model-service-catalog-row" role="row" key={model.id}>
                <strong>{model.model_key}</strong>
                <span>
                  {model.supported_efforts
                    .map((effort) => EFFORT_LABELS[effort])
                    .join(" · ")}
                </span>
                <span
                  className={classNames(
                    "model-validation-badge",
                    model.validation_status,
                  )}
                >
                  {model.active
                    ? (MODEL_STATUS_LABELS[model.validation_status] ?? "待验证")
                    : "已停用"}
                </span>
                {model.active && model.validation_status !== "validated" ? (
                  <button
                    className="text-button"
                    onClick={() => onValidateCatalogModel(model)}
                    disabled={Boolean(busy) || validationActive}
                  >
                    验证
                  </button>
                ) : (
                  <button className="text-button" onClick={onOpenModelCatalog}>
                    管理
                  </button>
                )}
              </div>
            ))
          ) : (
            <p className="model-service-catalog-empty">
              新增模型服务后，可在这里查看模型可用性。
            </p>
          )}
          {selectedConnection && visibleCatalogModels.length === 0 && (
            <p className="model-service-catalog-empty">
              当前接入未返回可用模型，请同步目录或检查接入权限。
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

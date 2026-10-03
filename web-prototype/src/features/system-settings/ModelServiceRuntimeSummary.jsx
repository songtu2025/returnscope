import {
  CaretDown,
  CheckCircle,
  Plus,
  Power,
  WarningCircle,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import { classNames } from "../../lib/presentation";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "activeVersion" | "availableModelCount" | "busy" | "validationActive" | "onStartValidation" | "onOpenNewConnection" | "onEditConnection" | "onEditLimits" | "onOpenVersions">} props */

export function ModelServiceRuntimeSummary({
  selectedConnection,
  activeVersion,
  availableModelCount,
  busy,
  validationActive,
  onStartValidation,
  onOpenNewConnection,
  onEditConnection,
  onEditLimits,
  onOpenVersions,
}) {
  const validated = activeVersion?.validation_status === "validated";
  return (
    <section className="content-card model-service-runtime">
      <div className={classNames("model-service-runtime-icon", validated && "online")}>
        {validated ? (
          <CheckCircle size={36} weight="duotone" />
        ) : (
          <WarningCircle size={36} weight="duotone" />
        )}
      </div>
      <ModelServiceRuntimeInfo
        selectedConnection={selectedConnection}
        activeVersion={activeVersion}
        availableModelCount={availableModelCount}
      />
      <ModelServiceRuntimeActions
        selectedConnection={selectedConnection}
        activeVersion={activeVersion}
        busy={busy}
        validationActive={validationActive}
        onStartValidation={onStartValidation}
        onOpenNewConnection={onOpenNewConnection}
        onEditConnection={onEditConnection}
        onEditLimits={onEditLimits}
        onOpenVersions={onOpenVersions}
      />
    </section>
  );
}

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "activeVersion" | "availableModelCount">} props */

function ModelServiceRuntimeInfo({
  selectedConnection,
  activeVersion,
  availableModelCount,
}) {
  const validationStatus = activeVersion?.validation_status;
  const statusLabel =
    validationStatus === "validated"
      ? "运行正常"
      : activeVersion
        ? "等待验证"
        : "尚未发布";
  return (
    <div className="model-service-runtime-main">
      <span className="asset-type">当前接入</span>
      <div className="model-service-runtime-title">
        <h2>{selectedConnection?.name ?? "尚未创建模型服务"}</h2>
        <span className={classNames("model-service-status", validationStatus)}>
          {statusLabel}
        </span>
      </div>
      <div className="model-service-runtime-meta">
        <span>
          服务地址 <b>{activeVersion?.base_url ?? "—"}</b>
        </span>
        <span>运行版本 {activeVersion ? "#" + activeVersion.version : "—"}</span>
        <span>{availableModelCount} 个可用模型</span>
      </div>
    </div>
  );
}

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "activeVersion" | "busy" | "validationActive" | "onStartValidation" | "onOpenNewConnection" | "onEditConnection" | "onEditLimits" | "onOpenVersions">} props */

function ModelServiceRuntimeActions({
  selectedConnection,
  activeVersion,
  busy,
  validationActive,
  onStartValidation,
  onOpenNewConnection,
  onEditConnection,
  onEditLimits,
  onOpenVersions,
}) {
  return (
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
        <Button
          autoInsertSpace={false}
          type="primary"
          icon={<Plus size={18} />}
          onClick={onOpenNewConnection}
          disabled={Boolean(busy)}
        >
          新增模型服务
        </Button>
      )}
      {selectedConnection && (
        <Button
          autoInsertSpace={false}
          size="small"
          type="link"
          onClick={onEditConnection}
          disabled={Boolean(busy)}
        >
          编辑连接
        </Button>
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
            <button
              type="button"
              role="menuitem"
              onClick={onEditLimits}
              disabled={Boolean(busy)}
            >
              请求限制
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={onOpenVersions}
              disabled={Boolean(busy)}
            >
              配置版本
            </button>
            {activeVersion && (
              <button
                type="button"
                role="menuitem"
                onClick={onOpenNewConnection}
                disabled={Boolean(busy)}
              >
                新增模型服务
              </button>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

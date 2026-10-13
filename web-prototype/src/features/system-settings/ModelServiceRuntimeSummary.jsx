import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import { CaretDown, Plus, Power } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { classNames } from "../../lib/presentation";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "activeVersion" | "busy" | "validationActive" | "onStartValidation" | "onOpenNewConnection" | "onEditConnection" | "onEditLimits" | "onOpenVersions">} props */

export function ModelServiceRuntimeSummary({
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
    <section className="content-card model-service-runtime">
      <ModelServiceRuntimeInfo
        selectedConnection={selectedConnection}
        activeVersion={activeVersion}
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

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "activeVersion">} props */

function ModelServiceRuntimeInfo({ selectedConnection, activeVersion }) {
  const validationStatus = activeVersion?.validation_status;
  const statusLabel =
    validationStatus === "validated"
      ? "上次验证通过"
      : activeVersion
        ? "等待验证"
        : "尚未发布";
  return (
    <div className="model-service-runtime-main">
      <div className="model-service-runtime-title">
        <h2>{selectedConnection?.name ?? "尚未创建模型服务"}</h2>
        <span className={classNames("model-service-status", validationStatus)}>
          {statusLabel}
        </span>
      </div>
      <p className="model-service-runtime-address" title={activeVersion?.base_url}>
        {activeVersion?.base_url ?? "—"}
      </p>
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
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu: true });
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
          type="link"
          onClick={onEditConnection}
          disabled={Boolean(busy)}
        >
          编辑连接
        </Button>
      )}
      {selectedConnection && (
        <details {...detailsProps} className="model-service-more">
          <summary {...summaryProps} role="button" aria-haspopup="menu">
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
              修改历史
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

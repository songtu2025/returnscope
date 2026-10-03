import { ArrowRight } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { EFFORT_LABELS, MODEL_STATUS_LABELS } from "../../constants";
import { classNames } from "../../lib/presentation";

const EFFORT_LABEL_MAP = /** @type {Record<string, string>} */ (EFFORT_LABELS);
const MODEL_STATUS_LABEL_MAP = /** @type {Record<string, string>} */ (
  MODEL_STATUS_LABELS
);

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceSummaryProps, "selectedConnection" | "visibleCatalogModels" | "busy" | "validationActive" | "onDiscoverModels" | "onOpenModelCatalog" | "onValidateCatalogModel">} props */

export function ModelServiceCatalogSummary({
  selectedConnection,
  visibleCatalogModels,
  busy,
  validationActive,
  onDiscoverModels,
  onOpenModelCatalog,
  onValidateCatalogModel,
}) {
  return (
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
          <Button
            autoInsertSpace={false}
            size="small"
            type="link"
            icon={<ArrowRight size={15} />}
            iconPlacement="end"
            onClick={onOpenModelCatalog}
            disabled={!selectedConnection || Boolean(busy)}
          >
            管理目录
          </Button>
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
                  .map((effort) => EFFORT_LABEL_MAP[effort] ?? effort)
                  .join(" · ")}
              </span>
              <span
                className={classNames(
                  "model-validation-badge",
                  model.validation_status,
                )}
              >
                {model.active
                  ? (MODEL_STATUS_LABEL_MAP[model.validation_status] ?? "待验证")
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
                <button
                  className="text-button"
                  onClick={onOpenModelCatalog}
                  disabled={Boolean(busy)}
                >
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
  );
}

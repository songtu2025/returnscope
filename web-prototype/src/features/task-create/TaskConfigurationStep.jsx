import {
  ArrowRight,
  CheckCircle,
  Database,
  GearSix,
  Pulse,
  UploadSimple,
} from "@phosphor-icons/react";
import { Confirmation, SectionTitle, SnapshotNotice } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";
import { classNames } from "../../lib/presentation";

export function TaskConfigurationStep({
  form,
  onFormChange,
  returns,
  selectedReturns,
  selectedProducts,
  onUploadReturns,
  publishedConfigs,
  selectedConfig,
  availableModels,
  modelPolicy,
  onConnectionChange,
  onModelPolicyChange,
  system,
  onGeneratePlan,
}) {
  return (
    <div className="task-create-layout">
      <section className="task-config-panel">
        <header className="task-config-header">
          <div>
            <span>任务配置</span>
            <h2>填写一次，系统自动拆分执行</h2>
            <p>结构化品类决定智能体路由，模型不会猜测已有商品信息。</p>
          </div>
          <span className="task-config-ready">
            <CheckCircle size={17} weight="fill" />
            运行条件已就绪
          </span>
        </header>

        <div className="task-config-section">
          <SectionTitle
            number="01"
            title="待分析数据"
            description="选择本次任务需要分析的退货明细版本。"
          />
          <div className="task-data-picker">
            <label className="task-config-choice">
              退货明细
              <select
                value={form.dataset_version_id}
                onChange={(event) =>
                  onFormChange({
                    ...form,
                    dataset_version_id: event.target.value,
                  })
                }
              >
                {returns.map((item) => (
                  <option key={item.version_id} value={item.version_id}>
                    {item.dataset_name} · v{item.version}
                    {item.version === item.current_version ? "（当前）" : ""} ·{" "}
                    {item.row_count.toLocaleString()} 行
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary-button task-data-upload"
              onClick={onUploadReturns}
            >
              <UploadSimple size={17} />
              导入退货明细
            </button>
          </div>
          <div className="task-data-readiness">
            {selectedProducts?.quality?.category_ready_rows != null && (
              <div
                className={classNames(
                  "task-data-quality",
                  selectedProducts.quality.missing_category_rows > 0
                    ? "warning"
                    : "ready",
                )}
              >
                <b>
                  品类A / 品类B就绪{" "}
                  {Number(
                    selectedProducts.quality.category_ready_rows || 0,
                  ).toLocaleString()}
                  /{selectedProducts.row_count.toLocaleString()} 行
                </b>
                <span>
                  缺少品类{" "}
                  {Number(
                    selectedProducts.quality.missing_category_rows || 0,
                  ).toLocaleString()}{" "}
                  行；未补齐时不能创建任务
                </span>
              </div>
            )}
            {selectedReturns?.quality?.matching_key_ready_rows != null && (
              <div
                className={classNames(
                  "task-data-quality",
                  selectedReturns.quality.missing_store_rows > 0 ||
                    selectedReturns.quality.missing_sku_rows > 0
                    ? "warning"
                    : "ready",
                )}
              >
                <b>
                  店铺/站点 + SKU 就绪{" "}
                  {Number(
                    selectedReturns.quality.matching_key_ready_rows || 0,
                  ).toLocaleString()}
                  /{selectedReturns.row_count.toLocaleString()} 行
                </b>
                <span>
                  缺失店铺/站点{" "}
                  {Number(
                    selectedReturns.quality.missing_store_rows || 0,
                  ).toLocaleString()}{" "}
                  行 · 缺失 SKU{" "}
                  {Number(
                    selectedReturns.quality.missing_sku_rows || 0,
                  ).toLocaleString()}{" "}
                  行
                </span>
              </div>
            )}
            <SnapshotNotice text="产品信息由系统统一维护并自动绑定；任务创建后会同时固化退货明细与产品信息版本。" />
          </div>
        </div>

        <div className="task-config-section">
          <SectionTitle
            number="02"
            title="任务与模型"
            description="任务名称可选；本次策略可覆盖你的默认偏好，任务创建后会固化为快照。"
          />
          <div className="task-model-context-grid">
            <label className="task-config-choice">
              任务名称（可选）
              <input
                value={form.title}
                onChange={(event) =>
                  onFormChange({ ...form, title: event.target.value })
                }
                maxLength="120"
                placeholder={`${selectedReturns?.dataset_name || "退货明细"} 语义分析`}
              />
            </label>
            <label className="task-config-choice">
              接入运行版本
              <select
                value={form.config_version_id}
                onChange={(event) => onConnectionChange(event.target.value)}
              >
                {publishedConfigs.map((config) => (
                  <option key={config.id} value={config.id}>
                    {config.connection_name} · {config.primary_model} · 推理强度
                    {EFFORT_LABELS[config.primary_effort] ?? config.primary_effort} ·
                    配置 #{config.version}
                  </option>
                ))}
              </select>
              <small>仅决定使用哪个已验证接入；不会覆盖下方的本次任务策略。</small>
            </label>
          </div>
          <div className="task-model-policy-grid">
            {[
              ["低成本初筛", "cheap_model", "cheap_effort", false],
              ["主分析", "primary_model", "primary_effort", true],
              ["风险复核", "secondary_model", "secondary_effort", false],
            ].map(([label, modelKey, effortKey, required]) => {
              const selectedModel = availableModels.find(
                (item) => item.model_key === modelPolicy[modelKey],
              );
              return (
                <label className="task-config-choice" key={modelKey}>
                  {label}
                  <select
                    value={modelPolicy[modelKey] || ""}
                    onChange={(event) => {
                      const model = availableModels.find(
                        (item) => item.model_key === event.target.value,
                      );
                      onModelPolicyChange({
                        [modelKey]: event.target.value,
                        [effortKey]: model?.supported_efforts.includes(
                          modelPolicy[effortKey],
                        )
                          ? modelPolicy[effortKey]
                          : (model?.supported_efforts[0] ?? "medium"),
                      });
                    }}
                  >
                    {!required && <option value="">不启用</option>}
                    {availableModels.map((model) => (
                      <option key={model.id} value={model.model_key}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                  {modelPolicy[modelKey] && (
                    <select
                      aria-label={`${label}推理强度`}
                      value={modelPolicy[effortKey]}
                      onChange={(event) =>
                        onModelPolicyChange({ [effortKey]: event.target.value })
                      }
                    >
                      {(selectedModel?.supported_efforts ?? []).map((effort) => (
                        <option key={effort} value={effort}>
                          推理强度{EFFORT_LABELS[effort] ?? effort}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              );
            })}
          </div>
          <div className="task-runtime-override">
            <label className="task-config-choice">
              本次初筛抽检比例（%）
              <input
                type="number"
                min="0"
                max="100"
                value={modelPolicy.cheap_audit_percent ?? 5}
                onChange={(event) =>
                  onModelPolicyChange({
                    cheap_audit_percent: Number(event.target.value),
                  })
                }
              />
              <small>
                默认来自模型服务；这里只影响本次任务，重新生成执行计划后会写入任务快照。
              </small>
            </label>
          </div>
          <p className="task-model-policy-note">
            模型选择可使用你的默认偏好；抽检比例属于运行参数，默认来自模型服务，这里的修改只作用于本次任务。
          </p>
        </div>
      </section>

      <aside className="task-create-summary">
        <div className="task-create-summary-heading">
          <span>运行摘要</span>
          <b>生成计划前确认</b>
          <p>下一步只做确定性检查，不会调用模型或产生模型费用。</p>
        </div>
        <button
          className="primary-button task-plan-button"
          disabled={!form.config_version_id}
          onClick={onGeneratePlan}
        >
          生成执行计划
          <ArrowRight size={18} />
        </button>
        <div className="task-create-confirmations">
          <Confirmation
            icon={Database}
            label="退货明细"
            value={selectedReturns?.dataset_name}
            note={`v${selectedReturns?.version} · ${selectedReturns?.row_count.toLocaleString()} 行`}
          />
          <Confirmation
            icon={GearSix}
            label="模型策略"
            value={modelPolicy.primary_model}
            note={`${selectedConfig?.connection_name} · 本次策略：${modelPolicy.cheap_model || "未启用"} / ${modelPolicy.primary_model} / ${modelPolicy.secondary_model || "未启用"} · 初筛抽检 ${modelPolicy.cheap_audit_percent ?? 5}%`}
          />
          <Confirmation
            icon={Pulse}
            label="我的并行名额"
            value={`${system?.my_running_tasks ?? 0}/3 已使用`}
            note={
              (system?.my_running_tasks ?? 0) >= 3
                ? "任务会先进入队列"
                : "可立即由后台领取"
            }
          />
        </div>
      </aside>
    </div>
  );
}

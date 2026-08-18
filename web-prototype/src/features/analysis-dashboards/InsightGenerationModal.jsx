import { WarningCircle } from "@phosphor-icons/react";

import { InlineLoading, Modal } from "../../components/SharedUi";
import { preferredInsightEffort } from "./insightModelOptions";

export function InsightGenerationModal({
  form,
  onChange,
  onClose,
  onSubmit,
  models,
  loading,
  submitting,
  error,
  ready,
  scopeLabel,
  includedRecords,
  unitCount,
  pendingRecords,
  excludedRecords,
}) {
  const selectedModel = models.find((model) => model.id === form.modelId);
  const supportedEfforts = selectedModel?.supported_efforts ?? [];
  const canSubmit =
    !loading &&
    !submitting &&
    !error &&
    ready &&
    includedRecords > 0 &&
    Boolean(form.modelId);

  const changeModel = (modelId) => {
    const model = models.find((item) => item.id === modelId);
    onChange({
      modelId,
      effort: model?.supported_efforts?.includes(form.effort)
        ? form.effort
        : preferredInsightEffort(model),
    });
  };

  return (
    <Modal
      className="insight-generation-modal"
      eyebrow=""
      title="生成 AI 洞察报告"
      description="确认本次分析范围和运行参数"
      onClose={onClose}
    >
      {loading ? (
        <InlineLoading label="正在核对数据范围与可用模型…" />
      ) : (
        <form className="insight-generation-form" onSubmit={onSubmit}>
          <div className="insight-generation-fields">
            <span className="insight-field-label">数据范围</span>
            <div className="insight-field-value">
              <b>{scopeLabel}</b>
              <small>
                已纳入 {includedRecords.toLocaleString()} 条可用退货记录
                {unitCount ? ` · ${unitCount.toLocaleString()} 个分类单元` : ""}
              </small>
            </div>

            <span className="insight-field-label">排除数据</span>
            <div className="insight-field-value">
              <b>
                待复核 {pendingRecords.toLocaleString()} 条、已排除{" "}
                {excludedRecords.toLocaleString()} 条
              </b>
              <small>不会参与本次报告生成</small>
            </div>

            <label className="insight-field-label" htmlFor="insight-model">
              模型
            </label>
            <div className="insight-field-value insight-model-field">
              <select
                id="insight-model"
                value={form.modelId}
                onChange={(event) => changeModel(event.target.value)}
              >
                {!models.length && <option value="">暂无可用模型</option>}
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.model_key}
                    {model.connection_name ? ` · ${model.connection_name}` : ""}
                  </option>
                ))}
              </select>
              <small>
                {models.length
                  ? "只展示已启用并验证通过的模型"
                  : "请先在系统设置中配置并验证模型"}
              </small>
            </div>

            <span className="insight-field-label">推理强度</span>
            <div className="insight-field-value">
              <div className="insight-effort-control" aria-label="推理强度">
                {[
                  ["low", "低"],
                  ["medium", "中"],
                  ["high", "高"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={form.effort === value}
                    disabled={!supportedEfforts.includes(value)}
                    onClick={() => onChange({ ...form, effort: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <small>报告默认使用高强度；实际模型和用量会随报告版本保存</small>
            </div>

            <span className="insight-field-label">运行方式</span>
            <div className="insight-field-value insight-inline-value">
              <b>后台生成，可离开当前页面</b>
              <small>返回报告页即可查看最新状态</small>
            </div>
          </div>

          {error && (
            <div className="insight-generation-error" role="alert">
              <WarningCircle size={17} />
              <span>{error}</span>
            </div>
          )}

          {!error && includedRecords <= 0 && (
            <div className="insight-generation-error" role="alert">
              <WarningCircle size={17} />
              <span>当前范围没有可用于生成报告的已审核记录。</span>
            </div>
          )}

          <div className="insight-generation-note" role="status">
            <WarningCircle size={17} />
            <span>报告绑定当前数据版本；后续数据变化不会改写历史报告。</span>
          </div>

          <footer className="insight-generation-actions">
            <div />
            <div>
              <button type="button" className="secondary-button" onClick={onClose}>
                取消
              </button>
              <button type="submit" className="primary-button" disabled={!canSubmit}>
                {submitting ? "正在提交…" : "开始生成"}
              </button>
            </div>
          </footer>
        </form>
      )}
    </Modal>
  );
}

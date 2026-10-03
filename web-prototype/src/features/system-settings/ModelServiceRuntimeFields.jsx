/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange"> & {formDisabled: boolean}} props */
export function ModelServiceRuntimeFields({ form, onFormChange, formDisabled }) {
  return (
    <>
      <div className="runtime-grid">
        <label>
          每分钟请求
          <input
            type="number"
            disabled={formDisabled}
            value={form.requests_per_minute}
            onChange={(event) =>
              onFormChange({
                ...form,
                requests_per_minute: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          单任务并发
          <input
            type="number"
            disabled={formDisabled}
            value={form.max_workers}
            onChange={(event) =>
              onFormChange({
                ...form,
                max_workers: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          请求超时（秒）
          <input
            type="number"
            disabled={formDisabled}
            value={form.timeout_seconds}
            onChange={(event) =>
              onFormChange({
                ...form,
                timeout_seconds: Number(event.target.value),
              })
            }
          />
        </label>
      </div>
      <div className="config-change-reason">
        <label>
          配置变更原因
          <textarea
            disabled={formDisabled}
            aria-label="配置变更原因"
            value={form.change_note ?? ""}
            onChange={(event) =>
              onFormChange({ ...form, change_note: event.target.value })
            }
            rows={3}
            maxLength={500}
            placeholder="必填：说明本次新增或调整配置的原因"
            required
          />
          {!form.change_note?.trim() && (
            <small className="config-field-error">请填写配置变更原因。</small>
          )}
        </label>
      </div>
    </>
  );
}

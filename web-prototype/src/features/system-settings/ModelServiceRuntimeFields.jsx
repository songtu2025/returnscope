/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange" | "onFieldBlur" | "touchedFields" | "configFormErrors"> & {formDisabled: boolean}} props */
export function ModelServiceRuntimeFields({
  form,
  onFormChange,
  formDisabled,
  onFieldBlur,
  touchedFields,
  configFormErrors,
}) {
  return (
    <>
      <div className="runtime-grid">
        <label>
          每分钟请求
          <input
            type="number"
            min={1}
            max={10000}
            onBlur={() => onFieldBlur("runtime")}
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
            min={1}
            max={16}
            onBlur={() => onFieldBlur("runtime")}
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
            min={5}
            max={600}
            onBlur={() => onFieldBlur("runtime")}
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
      {touchedFields.includes("runtime") && configFormErrors.length > 0 && (
        <p className="config-field-error" role="alert">
          {configFormErrors.join("；")}
        </p>
      )}
    </>
  );
}

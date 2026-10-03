import Input from "antd/es/input";
import { CardHeading } from "../../components/SharedUi";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange" | "selectedConnection" | "nameError" | "baseUrlError" | "apiKeyError"> & {formDisabled: boolean}} props */
export function ModelServiceConnectionFields({
  form,
  onFormChange,
  selectedConnection,
  nameError,
  baseUrlError,
  apiKeyError,
  formDisabled,
}) {
  return (
    <div className="config-section">
      <CardHeading title="连接信息" note="API 密钥加密保存在服务端" />
      <div className="config-fields">
        <label>
          接入名称
          <Input
            disabled={formDisabled}
            aria-label="接入名称"
            value={form.name}
            onChange={(event) => onFormChange({ ...form, name: event.target.value })}
            required
            aria-invalid={Boolean(nameError)}
            aria-describedby={nameError ? "model-service-name-error" : undefined}
          />
          {nameError && (
            <small
              id="model-service-name-error"
              className="config-field-error"
              role="alert"
            >
              {nameError}
            </small>
          )}
        </label>
        <label>
          协议
          <select
            disabled={formDisabled}
            value={form.provider}
            onChange={(event) =>
              onFormChange({ ...form, provider: event.target.value })
            }
          >
            <option value="responses-compatible">Responses compatible</option>
          </select>
        </label>
        <label>
          Base URL
          <input
            disabled={formDisabled}
            aria-label="Base URL"
            value={form.base_url}
            onChange={(event) =>
              onFormChange({ ...form, base_url: event.target.value })
            }
            placeholder="https://api.example.com/v1"
            aria-invalid={Boolean(baseUrlError)}
            aria-describedby={baseUrlError ? "model-service-base-url-error" : undefined}
          />
          {baseUrlError && (
            <small
              id="model-service-base-url-error"
              className="config-field-error"
              role="alert"
            >
              {baseUrlError}
            </small>
          )}
        </label>
        <label>
          API 密钥
          <input
            type="password"
            disabled={formDisabled}
            aria-label="API 密钥"
            value={form.api_key}
            onChange={(event) => onFormChange({ ...form, api_key: event.target.value })}
            placeholder={selectedConnection ? "留空则沿用原密钥" : "sk-…"}
            aria-invalid={Boolean(apiKeyError)}
            aria-describedby={apiKeyError ? "model-service-api-key-error" : undefined}
          />
          {apiKeyError && (
            <small
              id="model-service-api-key-error"
              className="config-field-error"
              role="alert"
            >
              {apiKeyError}
            </small>
          )}
        </label>
      </div>
    </div>
  );
}

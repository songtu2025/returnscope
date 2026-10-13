import Input from "antd/es/input";
import { CardHeading } from "../../components/SharedUi";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange" | "selectedConnection" | "nameError" | "baseUrlError" | "apiKeyError" | "onFieldBlur"> & {formDisabled: boolean}} props */
export function ModelServiceConnectionFields({
  form,
  onFormChange,
  selectedConnection,
  nameError,
  baseUrlError,
  apiKeyError,
  formDisabled,
  onFieldBlur,
}) {
  return (
    <div className="config-section">
      <CardHeading title="连接信息" />
      <div className="config-fields">
        <label>
          接入名称
          <Input
            disabled={formDisabled}
            aria-label="接入名称"
            value={form.name}
            onChange={(event) => onFormChange({ ...form, name: event.target.value })}
            required
            onBlur={() => onFieldBlur("name")}
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
            onBlur={() => onFieldBlur("base_url")}
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
            placeholder={
              selectedConnection?.versions?.length
                ? "留空则沿用原密钥"
                : "输入接入方提供的 API 密钥"
            }
            onBlur={() => onFieldBlur("api_key")}
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

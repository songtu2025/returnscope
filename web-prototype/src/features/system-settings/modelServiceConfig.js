import { EFFORT_LABELS } from "../../constants";

/** @typedef {import("./modelServiceViewContracts").CatalogModel} CatalogModel */
/** @typedef {import("./modelServiceViewContracts").ModelOption} ModelOption */
/** @typedef {import("./modelServiceViewContracts").ModelServiceForm} ModelServiceForm */
/** @typedef {import("./modelServiceViewContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("./modelServiceViewContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").ConfigDiffKey} ConfigDiffKey */

const EFFORT_LABEL_MAP = /** @type {Record<string, string>} */ (EFFORT_LABELS);

/** @type {Array<[ConfigDiffKey, string]>} */
const CONFIG_DIFF_FIELDS = [
  ["base_url", "Base URL"],
  ["requests_per_minute", "每分钟请求"],
  ["max_workers", "单任务并发"],
  ["timeout_seconds", "请求超时"],
];

/** @type {ModelServiceForm} */
export const EMPTY_MODEL_SERVICE_FORM = {
  name: "",
  provider: "responses-compatible",
  base_url: "",
  api_key: "",
  primary_model: "",
  primary_effort: "medium",
  cheap_model: null,
  cheap_effort: "low",
  secondary_model: null,
  secondary_effort: "high",
  cheap_audit_percent: 5,
  requests_per_minute: 60,
  max_workers: 4,
  timeout_seconds: 120,
  change_note: "",
};

/**
 * @param {ModelConnection} connection
 * @param {string | null | undefined} selectedVersionId
 * @param {string | null} focusConfigVersionId
 * @returns {ConfigVersion | null}
 */
export function preferredVersion(connection, selectedVersionId, focusConfigVersionId) {
  return (
    connection.versions?.find(
      (version) => String(version.id) === String(focusConfigVersionId),
    ) ??
    connection.versions?.find((version) => version.id === selectedVersionId) ??
    connection.versions?.find(
      (version) => version.id !== connection.active_version_id && !version.published_at,
    ) ??
    connection.active_version ??
    connection.versions?.[0] ??
    null
  );
}

/**
 * @param {ModelConnection | null | undefined} connection
 * @param {ConfigVersion} version
 * @param {boolean} [resetChangeNote]
 * @returns {ModelServiceForm}
 */
export function formForVersion(connection, version, resetChangeNote = false) {
  return {
    ...EMPTY_MODEL_SERVICE_FORM,
    ...version,
    name: connection?.name ?? "",
    api_key: "",
    connection_id: connection?.id,
    ...(resetChangeNote ? { change_note: "" } : {}),
  };
}

/** @param {CatalogModel[]} catalogModels @param {ModelServiceForm} form @returns {ModelOption[]} */
export function createModelOptions(catalogModels, form) {
  const historicalModelKeys = [];
  if (form.cheap_model) historicalModelKeys.push(form.cheap_model);
  if (form.primary_model) historicalModelKeys.push(form.primary_model);
  if (form.secondary_model) historicalModelKeys.push(form.secondary_model);
  return [
    ...catalogModels,
    ...historicalModelKeys
      .filter(
        (modelKey) => !catalogModels.some((model) => model.model_key === modelKey),
      )
      .map((modelKey) => ({
        id: `historical-${modelKey}`,
        model_key: modelKey,
        display_name: modelKey,
        supported_efforts: ["low", "medium", "high"],
        active: false,
        historical: true,
      })),
  ];
}

/** @param {string} value */
function getBaseUrlError(value) {
  const baseUrl = value.trim();
  if (!baseUrl) return "请填写 Base URL。";
  try {
    const parsed = new URL(baseUrl);
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
      return "Base URL 必须是有效的 HTTP 或 HTTPS 地址。";
    }
    if (
      parsed.protocol !== "https:" &&
      !["127.0.0.1", "localhost"].includes(parsed.hostname)
    ) {
      return "非本地 API 必须使用 HTTPS。";
    }
  } catch {
    return "Base URL 必须是有效的 HTTP 或 HTTPS 地址。";
  }
  return "";
}

/** @param {string} key @param {unknown} value */
export function configValue(key, value) {
  if (key.endsWith("_effort")) {
    const effort = value == null ? "" : String(value);
    return (EFFORT_LABEL_MAP[effort] ?? effort) || "未设置";
  }
  return value === null || value === undefined || value === ""
    ? "未设置"
    : String(value);
}

/** @param {unknown} error */
export function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/**
 * @param {ConfigVersion} left
 * @param {ConfigVersion | null} right
 * @param {string} key
 */
function configValuesDiffer(left, right, key) {
  if (!right) return false;
  if (key === "base_url") return left.base_url !== right.base_url;
  if (key === "requests_per_minute")
    return left.requests_per_minute !== right.requests_per_minute;
  if (key === "max_workers") return left.max_workers !== right.max_workers;
  if (key === "timeout_seconds") return left.timeout_seconds !== right.timeout_seconds;
  return false;
}

/** @param {ModelServiceForm} form @param {boolean} editing @param {boolean} hasConnection */
export function getConfigFormState(form, editing, hasConnection) {
  if (!editing) {
    return { nameError: "", baseUrlError: "", apiKeyError: "", configFormErrors: [] };
  }
  const nameError = !form.name?.trim() ? "请填写接入名称。" : "";
  const baseUrlError = getBaseUrlError(form.base_url);
  const apiKeyError =
    !hasConnection && !form.api_key?.trim() ? "请填写 API 密钥。" : "";
  const configFormErrors = [
    nameError,
    baseUrlError,
    apiKeyError,
    !form.primary_model ? "请选择验证模型。" : "",
    !form.change_note?.trim() ? "请填写配置变更原因。" : "",
  ].filter(Boolean);
  return { nameError, baseUrlError, apiKeyError, configFormErrors };
}

/** @param {ModelConnection | undefined} selectedConnection @param {ConfigVersion | null} selectedVersion */
export function getConfigVersionState(selectedConnection, selectedVersion) {
  const previousVersion = selectedConnection?.versions?.find(
    (version) => version.version === (selectedVersion?.version ?? 1) - 1,
  );
  const versionChanges = previousVersion
    ? CONFIG_DIFF_FIELDS.filter(([key]) =>
        configValuesDiffer(previousVersion, selectedVersion, key),
      )
    : [];
  const selectedVersionIsActive =
    selectedConnection?.active_version_id === selectedVersion?.id;
  return { previousVersion, versionChanges, selectedVersionIsActive };
}

/**
 * @param {import("../../shared/api/systemSettingsContracts").ModelDraft} draft
 * @param {import("../../shared/api/systemSettingsContracts").ModelEditorMode | null} mode
 * @param {CatalogModel[]} catalogModels
 */
export function getModelDraftError(draft, mode, catalogModels) {
  const modelKey = draft.model_key.trim();
  if (!modelKey) return "请填写模型 ID";
  if (!draft.supported_efforts.length) return "至少选择一种推理强度";
  if (mode !== "create" && !draft.id) return "模型数据无效";
  if (
    mode === "create" &&
    catalogModels.some((model) => model.model_key === modelKey)
  ) {
    return "该模型 ID 已存在";
  }
  return "";
}

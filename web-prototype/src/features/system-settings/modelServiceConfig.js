import { EFFORT_LABELS } from "../../constants";

export const CONFIG_DIFF_FIELDS = [
  ["base_url", "Base URL"],
  ["requests_per_minute", "每分钟请求"],
  ["max_workers", "单任务并发"],
  ["timeout_seconds", "请求超时"],
];

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

export function createDefaultModelCatalog() {
  return [];
}

export function createModelOptions(catalogModels, form) {
  const historicalModelKeys = [
    form.cheap_model,
    form.primary_model,
    form.secondary_model,
  ].filter(Boolean);
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

export function getBaseUrlError(value) {
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

export function configValue(key, value) {
  if (key.endsWith("_effort")) return EFFORT_LABELS[value] ?? value ?? "未设置";
  return value === null || value === undefined || value === ""
    ? "未设置"
    : String(value);
}

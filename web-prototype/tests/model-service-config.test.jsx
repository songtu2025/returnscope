import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    configs: vi.fn(),
    activeValidation: vi.fn(),
    startModelValidation: vi.fn(),
    validationEventUrl: vi.fn(),
    validationRun: vi.fn(),
    createConfig: vi.fn(),
    discardConfig: vi.fn(),
    createModel: vi.fn(),
    discoverModels: vi.fn(),
    updateModel: vi.fn(),
    publishConfig: vi.fn(),
    startConfigValidation: vi.fn(),
  },
}));
vi.mock("../src/shared/api/modelApi", () => ({ modelApi: apiMock }));

import { ModelServicePage } from "../src/features/system-settings/ModelServicePage";

beforeEach(() => {
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.configs.mockResolvedValue([]);
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.validationEventUrl.mockReturnValue("/validation-events");
});
afterEach(() => cleanup());

test("模型服务编辑态说明保存禁用原因并就近校验地址", async () => {
  const user = userEvent.setup();
  render(<ModelServicePage notify={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: "新增模型服务" }));

  const availableModelsHeading = screen.getByRole("heading", { name: "可用模型" });
  expect(availableModelsHeading).toBeVisible();
  expect(availableModelsHeading.closest(".model-service-editor")).toHaveClass(
    "is-new-connection",
  );
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(
    screen.getByPlaceholderText("例如 deepseek-reasoner"),
    "provider-model",
  );
  await user.click(screen.getByRole("button", { name: "保存模型" }));
  expect(screen.getAllByText("provider-model")[0]).toBeVisible();
  await user.selectOptions(screen.getByLabelText("模型"), "provider-model");

  const saveButton = screen.getByRole("button", { name: "保存草稿" });
  const baseUrlInput = screen.getByLabelText("Base URL");
  expect(saveButton).toBeDisabled();
  expect(screen.getAllByText("请填写接入名称。").length).toBeGreaterThan(0);
  expect(screen.getAllByText("请填写 API 密钥。").length).toBeGreaterThan(0);
  expect(screen.queryByText("请选择验证模型。")).not.toBeInTheDocument();
  expect(screen.getAllByText("请填写配置变更原因。").length).toBeGreaterThan(0);
  expect(baseUrlInput).toHaveAttribute("aria-invalid", "true");
  expect(baseUrlInput).toHaveAttribute(
    "aria-describedby",
    "model-service-base-url-error",
  );

  await user.type(baseUrlInput, "http://api.example.com");
  expect(screen.getByText("非本地 API 必须使用 HTTPS。")).toBeVisible();

  await user.clear(baseUrlInput);
  await user.type(baseUrlInput, "https://api.example.com/v1");
  expect(screen.queryByText("非本地 API 必须使用 HTTPS。")).not.toBeInTheDocument();
  expect(baseUrlInput).toHaveAttribute("aria-invalid", "false");

  await user.type(screen.getByLabelText("配置变更原因"), "新增生产接入");
  expect(screen.getByRole("status")).toHaveTextContent("请填写接入名称。");
  await user.type(screen.getByLabelText("接入名称"), "生产模型服务");
  expect(screen.getByRole("status")).toHaveTextContent("请填写 API 密钥。");
  await user.type(screen.getByLabelText("API 密钥"), "test-api-key");
  expect(saveButton).toBeEnabled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("模型服务通用控件保留可访问名称和受控输入", async () => {
  const user = userEvent.setup();
  render(<ModelServicePage notify={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: "新增模型服务" }));
  const connectionName = screen.getByRole("textbox", { name: "接入名称" });
  await user.type(connectionName, "生产线路");
  expect(connectionName).toHaveValue("生产线路");
  expect(screen.getByRole("button", { name: "取消", exact: true })).toBeVisible();

  await user.click(screen.getByRole("button", { name: "添加模型" }));
  const dialog = screen.getByRole("dialog", { name: "添加模型" });
  const displayName = within(dialog).getByRole("textbox", { name: "显示名称" });
  await user.type(displayName, "主分析模型");
  expect(displayName).toHaveValue("主分析模型");
  expect(
    within(dialog).getByRole("button", { name: "取消", exact: true }),
  ).toBeVisible();
});

test("模型服务摘要展示未发布草稿并保留按需编辑入口", async () => {
  const user = userEvent.setup();
  const activeVersion = {
    id: "cfg-1",
    connection_id: "conn-1",
    version: 1,
    base_url: "https://api.example.com/v1",
    primary_model: "gpt-main",
    primary_effort: "medium",
    cheap_model: "gpt-cheap",
    cheap_effort: "low",
    secondary_model: "gpt-review",
    secondary_effort: "high",
    validation_status: "validated",
    validated_at: "2026-08-10T08:00:00Z",
    published_at: "2026-08-10T08:10:00Z",
  };
  const draftVersion = {
    ...activeVersion,
    id: "cfg-2",
    version: 2,
    validation_status: "failed",
    validation_message: "验证失败",
    change_note: "调整风险复核模型",
    published_at: null,
  };
  apiMock.configs.mockResolvedValue([
    {
      id: "conn-1",
      name: "生产模型服务",
      provider: "responses-compatible",
      active_version_id: "cfg-1",
      active_version: activeVersion,
      versions: [draftVersion, activeVersion],
      models: [],
    },
  ]);

  render(<ModelServicePage notify={vi.fn()} />);

  expect(await screen.findByText("草稿 #2 · 验证失败")).toBeVisible();
  expect(screen.getByText(/当前运行 #1 不受影响/)).toBeVisible();
  expect(screen.getByRole("button", { name: "继续处理" })).toBeVisible();
  expect(screen.getByRole("button", { name: "验证服务" })).toBeVisible();
  expect(screen.queryByDisplayValue(/sk-/)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "继续处理" }));
  expect(screen.getByRole("heading", { name: "连接信息" })).toBeVisible();
  expect(screen.getByLabelText("API 密钥")).toHaveValue("");
  expect(screen.getByRole("button", { name: "取消" })).toBeVisible();
});

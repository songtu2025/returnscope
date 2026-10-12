import { cleanup, render, screen, within, waitFor } from "@testing-library/react";
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

  const availableModelsHeading = screen.getByRole("heading", { name: "模型目录" });
  expect(availableModelsHeading).toBeVisible();
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(
    screen.getByPlaceholderText("输入接入方提供的模型 ID"),
    "provider-model",
  );
  await user.click(screen.getByRole("button", { name: "保存模型" }));
  expect(screen.getAllByText("provider-model")[0]).toBeVisible();
  await user.selectOptions(screen.getByLabelText("模型"), "provider-model");

  const saveButton = screen.getByRole("button", { name: "保存草稿" });
  const baseUrlInput = screen.getByLabelText("Base URL");
  expect(saveButton).toBeDisabled();
  expect(screen.queryByText("请填写接入名称。")).not.toBeInTheDocument();
  expect(screen.queryByText("请填写 API 密钥。")).not.toBeInTheDocument();
  expect(screen.queryByText("请选择验证模型。")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("配置变更原因")).not.toBeInTheDocument();
  expect(baseUrlInput).toHaveAttribute("aria-invalid", "false");

  await user.type(baseUrlInput, "http://api.example.com");
  await user.tab();
  expect(screen.getByText("非本地 API 必须使用 HTTPS。")).toBeVisible();
  expect(baseUrlInput).toHaveAttribute(
    "aria-describedby",
    "model-service-base-url-error",
  );

  await user.clear(baseUrlInput);
  await user.type(baseUrlInput, "https://api.example.com/v1");
  expect(screen.queryByText("非本地 API 必须使用 HTTPS。")).not.toBeInTheDocument();
  expect(baseUrlInput).toHaveAttribute("aria-invalid", "false");

  await user.type(screen.getByLabelText("接入名称"), "生产模型服务");
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
  expect(screen.getByText(/已发布配置 #1 继续供新任务使用/)).toBeVisible();
  expect(screen.getByRole("button", { name: "验证草稿" })).toBeVisible();
  expect(screen.getByText("上次验证通过")).toBeVisible();
  expect(screen.getByRole("button", { name: "验证服务" })).toBeVisible();
  expect(screen.queryByDisplayValue(/sk-/)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "编辑草稿" }));
  expect(screen.getByRole("heading", { name: "连接信息" })).toBeVisible();
  expect(screen.getByLabelText("API 密钥")).toHaveValue("");
  expect(screen.getByRole("button", { name: "取消" })).toBeVisible();
  expect(screen.queryByText("配置变更原因")).not.toBeInTheDocument();
  expect(screen.getByText("未保存修改，保存后验证")).toBeVisible();
});

test("新建服务保存后选中新服务，验证保存的草稿后才能发布", async () => {
  const user = userEvent.setup();
  const old = {
    id: "old",
    name: "原服务",
    models: [],
    versions: [],
    active_version: null,
  };
  const draft = {
    id: "new-cfg",
    connection_id: "new",
    version: 1,
    base_url: "https://api.example.com/v1",
    primary_model: "provider-model",
    primary_effort: "medium",
    requests_per_minute: 60,
    max_workers: 4,
    timeout_seconds: 120,
    validation_status: "draft",
    published_at: null,
  };
  const current = {
    id: "new",
    name: "新增服务",
    models: [
      {
        id: "new-model",
        model_key: "provider-model",
        display_name: "provider-model",
        supported_efforts: ["medium"],
        active: true,
        validation_status: "draft",
      },
    ],
    versions: [draft],
    active_version: null,
  };
  apiMock.configs.mockResolvedValueOnce([old]).mockResolvedValue([current, old]);
  apiMock.createConfig.mockResolvedValue(draft);
  apiMock.startConfigValidation.mockResolvedValue({
    id: "run-new",
    kind: "config",
    target_id: draft.id,
    config_version_id: draft.id,
    status: "passed",
    total_count: 1,
    completed_count: 1,
    items: [],
    endpoint: "https://api.example.com/v1/responses",
    timeout_seconds: 120,
  });
  apiMock.publishConfig.mockResolvedValue({
    ...draft,
    published_at: "2026-10-12T08:00:00Z",
  });
  render(<ModelServicePage notify={vi.fn()} focusConnectionId="old" />);
  await user.click(await screen.findByRole("button", { name: "新增模型服务" }));
  await user.type(screen.getByLabelText("接入名称"), "新增服务");
  await user.type(screen.getByLabelText("Base URL"), draft.base_url);
  await user.type(screen.getByLabelText("API 密钥"), "synthetic-key");
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(screen.getByRole("textbox", { name: /^模型 ID/ }), "provider-model");
  await user.click(screen.getByRole("button", { name: "保存模型" }));
  await user.selectOptions(screen.getByLabelText("模型"), "provider-model");
  await user.click(screen.getByRole("button", { name: "保存草稿" }));
  expect(await screen.findByRole("heading", { name: "新增服务" })).toBeVisible();
  expect(screen.getByRole("button", { name: "发布为当前配置" })).toBeDisabled();
  expect(apiMock.createConfig.mock.calls[0][0]).toMatchObject({
    connection_id: null,
    cheap_model: null,
    secondary_model: null,
  });
  await user.click(screen.getByRole("button", { name: "验证连接与模型" }));
  await waitFor(() =>
    expect(apiMock.startConfigValidation).toHaveBeenCalledWith("new-cfg"),
  );
  expect(screen.getByText("配置 #1 · 1 个模型")).toBeVisible();
  apiMock.configs.mockResolvedValue([
    { ...current, versions: [{ ...draft, validation_status: "validated" }] },
    old,
  ]);
  // 验证结果由后台刷新带回，页面不凭本地点击状态放开发布。
  window.dispatchEvent(new Event("focus"));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "发布为当前配置" })).toBeEnabled(),
  );
  await user.click(screen.getByRole("button", { name: "发布为当前配置" }));
  await waitFor(() => expect(apiMock.publishConfig).toHaveBeenCalledWith("new-cfg"));
  await user.click(screen.getByRole("button", { name: "返回服务摘要" }));
  await user.click(screen.getByRole("button", { name: "编辑连接" }));
  await user.type(screen.getByLabelText("接入名称"), "再次调整");
  const nextDraft = { ...draft, id: "new-cfg-2", version: 2 };
  apiMock.createConfig.mockResolvedValue(nextDraft);
  apiMock.configs.mockResolvedValue([
    { ...current, versions: [nextDraft, draft] },
    old,
  ]);
  await user.click(screen.getByRole("button", { name: "保存草稿" }));
  await screen.findByRole("heading", { name: "验证连接与选定模型" });
  expect(screen.queryByText("配置 #1 · 1 个模型")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "发布为当前配置" })).toBeDisabled();
});

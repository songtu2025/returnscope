import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
import { ModelServiceCatalogSummary } from "../src/features/system-settings/ModelServiceCatalogSummary";

beforeEach(() => {
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.configs.mockResolvedValue([]);
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.validationEventUrl.mockReturnValue("/validation-events");
});
afterEach(() => cleanup());

test("摘要仅保留目录总入口，待验证模型提供对应行验证", async () => {
  const user = userEvent.setup();
  const models = [
    { id: "ready", active: true, validation_status: "validated" },
    { id: "pending", active: true, validation_status: "draft" },
    { id: "inactive", active: false, validation_status: "draft" },
  ].map((model) => ({
    ...model,
    model_key: model.id,
    supported_efforts: ["medium"],
  }));
  const onOpenModelCatalog = vi.fn();
  const onValidateCatalogModel = vi.fn();
  render(
    <ModelServiceCatalogSummary
      selectedConnection={{ id: "connection" }}
      visibleCatalogModels={models}
      busy=""
      validationActive={false}
      onDiscoverModels={vi.fn()}
      onOpenModelCatalog={onOpenModelCatalog}
      onValidateCatalogModel={onValidateCatalogModel}
    />,
  );

  expect(screen.queryByRole("button", { name: "管理" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "管理目录" })).toHaveLength(1);
  const rows = screen.getAllByRole("row");
  expect(within(rows[1]).queryByRole("button")).not.toBeInTheDocument();
  expect(within(rows[3]).queryByRole("button")).not.toBeInTheDocument();
  await user.click(within(rows[2]).getByRole("button", { name: "验证" }));
  expect(onValidateCatalogModel).toHaveBeenCalledExactlyOnceWith(models[1]);
  expect(onOpenModelCatalog).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "管理目录" }));
  expect(onOpenModelCatalog).toHaveBeenCalledTimes(1);
});

test("用户可以从模型列表启动真实验证", async () => {
  const user = userEvent.setup();
  const version = {
    id: "cfg-1",
    connection_id: "conn-1",
    version: 1,
    base_url: "https://api.example.com/v1",
    primary_model: "gpt-main",
    primary_effort: "medium",
    cheap_model: null,
    cheap_effort: "low",
    secondary_model: null,
    secondary_effort: "high",
    requests_per_minute: 60,
    max_workers: 4,
    timeout_seconds: 120,
    cheap_audit_percent: 5,
    validation_status: "validated",
    validation_message: "验证通过",
    change_note: "初始配置",
    creator_name: "管理员",
    created_at: "2026-08-10T08:00:00Z",
    validated_at: "2026-08-10T08:00:00Z",
  };
  apiMock.configs.mockResolvedValue([
    {
      id: "conn-1",
      name: "生产线路",
      provider: "responses-compatible",
      active_version_id: "cfg-1",
      active_version: version,
      versions: [version],
      models: [
        {
          id: "model-1",
          connection_id: "conn-1",
          model_key: "gpt-main",
          display_name: "主分析模型",
          supported_efforts: ["medium"],
          active: true,
          validation_status: "validated",
          validation_message: "验证通过",
        },
      ],
    },
  ]);
  apiMock.startModelValidation.mockResolvedValue({
    id: "validation-1",
    kind: "model",
    target_id: "model-1",
    status: "queued",
    stage: "queued",
    total_count: 1,
    completed_count: 0,
    created_at: "2026-08-10T08:00:00Z",
    endpoint: "https://api.example.com/v1/responses",
    timeout_seconds: 120,
    created_by_name: "管理员",
    items: [
      {
        model_id: "model-1",
        model_key: "gpt-main",
        display_name: "主分析模型",
        role: "单模型验证",
        effort: "medium",
        status: "pending",
        message: "等待验证",
        started_at: null,
        duration_ms: null,
        http_status: null,
      },
    ],
  });

  render(<ModelServicePage notify={vi.fn()} />);

  expect(screen.getByRole("heading", { name: "模型服务" })).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "智能体模型策略" }),
  ).not.toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: /管理目录/ }));
  expect(screen.getByRole("heading", { name: "模型目录" })).toBeVisible();
  expect(screen.getAllByRole("button", { name: "添加模型" })).toHaveLength(1);
  expect(screen.queryByText("连接信息")).not.toBeInTheDocument();
  expect((await screen.findAllByText("gpt-main"))[0]).toBeVisible();
  await user.click(screen.getByRole("button", { name: "验证" }));

  await waitFor(() =>
    expect(apiMock.startModelValidation).toHaveBeenCalledWith("model-1"),
  );
  expect((await screen.findAllByText("单模型验证"))[0]).toBeVisible();
});

test("模型服务仅保留接入方同步后的可用模型", async () => {
  const user = userEvent.setup();
  const version = {
    id: "cfg-1",
    connection_id: "conn-1",
    version: 1,
    base_url: "https://api.example.com/v1",
    primary_model: "provider-model",
    primary_effort: "medium",
    validation_status: "validated",
  };
  const connection = (models) => [
    {
      id: "conn-1",
      name: "生产线路",
      provider: "responses-compatible",
      active_version_id: "cfg-1",
      active_version: version,
      versions: [version],
      models,
    },
  ];
  apiMock.configs
    .mockResolvedValueOnce(
      connection([
        {
          id: "model-old",
          model_key: "gpt-5.6",
          display_name: "gpt-5.6",
          supported_efforts: ["medium"],
          active: true,
          validation_status: "validated",
        },
      ]),
    )
    .mockResolvedValueOnce(
      connection([
        {
          id: "model-old",
          model_key: "gpt-5.6",
          display_name: "gpt-5.6",
          supported_efforts: ["medium"],
          active: false,
          validation_status: "validated",
        },
        {
          id: "model-provider",
          model_key: "provider-model",
          display_name: "provider-model",
          supported_efforts: ["medium"],
          active: true,
          validation_status: "draft",
        },
      ]),
    );
  apiMock.discoverModels.mockResolvedValue({ count: 1 });

  render(<ModelServicePage notify={vi.fn()} />);

  await user.click(await screen.findByRole("button", { name: "同步目录" }));
  expect(apiMock.discoverModels).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "取消", exact: true }));
  expect(apiMock.discoverModels).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "同步目录" }));
  await user.click(screen.getByRole("button", { name: "确认同步" }));
  await waitFor(() => expect(apiMock.discoverModels).toHaveBeenCalledWith("conn-1"));
  expect(await screen.findByText("provider-model")).toBeVisible();
  expect(screen.queryByText("gpt-5.6")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "管理目录" }));
  await user.click(screen.getByRole("checkbox", { name: "显示停用模型" }));
  expect(screen.getAllByText("gpt-5.6")[0]).toBeVisible();
});

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { requestNavigation } from "../src/app/navigationGuard";
const api = vi.hoisted(() => ({
  configs: vi.fn(),
  activeValidation: vi.fn(),
  createConfig: vi.fn(),
  publishConfig: vi.fn(),
  startConfigValidation: vi.fn(),
  createModel: vi.fn(),
}));
vi.mock("../src/shared/api/modelApi", () => ({ modelApi: api }));
import { ModelServicePage } from "../src/features/system-settings/ModelServicePage";
const version = {
  id: "version",
  connection_id: "connection",
  version: 1,
  base_url: "https://api.example.com",
  primary_model: "main",
  primary_effort: "medium",
  requests_per_minute: 60,
  max_workers: 3,
  timeout_seconds: 120,
  validation_status: "validated",
  published_at: "2026-10-01T00:00:00Z",
};
beforeEach(() => {
  Object.values(api).forEach((mock) => mock.mockReset());
  api.configs.mockResolvedValue([
    {
      id: "connection",
      name: "服务",
      active_version_id: "version",
      active_version: version,
      versions: [version],
      models: [],
    },
  ]);
  api.activeValidation.mockResolvedValue(null);
  api.createConfig.mockResolvedValue({
    ...version,
    id: "draft",
    version: 2,
    published_at: null,
  });
});
afterEach(cleanup);
test("服务路由退出仅保存连接草稿，失败保留输入，不验证或发布", async () => {
  const user = userEvent.setup();
  const proceed = vi.fn();
  api.createConfig.mockRejectedValueOnce(new Error("连接保存失败"));
  render(<ModelServicePage notify={vi.fn()} />);
  await user.click(await screen.findByRole("button", { name: "编辑连接" }));
  await user.type(screen.getByLabelText("接入名称"), " 修改");
  act(() => requestNavigation(proceed));
  const dialog = screen.getByRole("dialog", { name: "修改尚未保存" });
  await user.click(within(dialog).getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(within(dialog).getByRole("button", { name: "保存后离开" })).toBeEnabled(),
  );
  expect(proceed).not.toHaveBeenCalled();
  expect(screen.getByLabelText("接入名称")).toHaveValue("服务 修改");
  await user.click(within(dialog).getByRole("button", { name: "保存后离开" }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(api.createConfig).toHaveBeenCalledTimes(2);
  expect(api.publishConfig).not.toHaveBeenCalled();
  expect(api.startConfigValidation).not.toHaveBeenCalled();
});
test("服务修改后再改回不拦截，取消退出保留当前连接编辑", async () => {
  render(<ModelServicePage notify={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "编辑连接" }));
  fireEvent.change(screen.getByLabelText("接入名称"), { target: { value: "新名称" } });
  act(() => requestNavigation(vi.fn()));
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("接入名称")).toHaveValue("新名称");
  fireEvent.change(screen.getByLabelText("接入名称"), { target: { value: "服务" } });
  expect(requestNavigation(vi.fn())).toBe(true);
});
test("新连接未完成的模型草稿不伪称全量保存，明确引导并保留模型输入", async () => {
  api.configs.mockResolvedValue([]);
  const notify = vi.fn();
  render(<ModelServicePage notify={notify} />);
  fireEvent.click(await screen.findByRole("button", { name: "新增模型服务" }));
  fireEvent.click(screen.getByRole("button", { name: "添加模型" }));
  fireEvent.change(screen.getByPlaceholderText("输入接入方提供的模型 ID"), {
    target: { value: "unsaved-model" },
  });
  const proceed = vi.fn();
  act(() => requestNavigation(proceed));
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(notify).toHaveBeenCalledWith(
      expect.stringContaining("请先完成模型编辑"),
      "error",
    ),
  );
  expect(proceed).not.toHaveBeenCalled();
  expect(api.createConfig).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByPlaceholderText("输入接入方提供的模型 ID")).toHaveValue(
    "unsaved-model",
  );
});

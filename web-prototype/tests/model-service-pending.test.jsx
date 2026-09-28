import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    configs: vi.fn(),
    activeValidation: vi.fn(),
    createConfig: vi.fn(),
    publishConfig: vi.fn(),
    discardConfig: vi.fn(),
    discoverModels: vi.fn(),
    createModel: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({ api: apiMock }));

import { ApiManagement } from "../src/pages/ApiManagement";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function connection(id, withDraft = false) {
  const activeVersion = {
    id: `${id}-version-1`,
    connection_id: id,
    version: 1,
    base_url: "https://api.example.com/v1",
    primary_model: "example-model",
    primary_effort: "medium",
    requests_per_minute: 60,
    max_workers: 4,
    timeout_seconds: 120,
    validation_status: "validated",
    published_at: "2026-09-01T00:00:00Z",
  };
  const draftVersion = withDraft
    ? {
        ...activeVersion,
        id: `${id}-version-2`,
        version: 2,
        change_note: "调整配置",
        published_at: null,
      }
    : null;
  return {
    id,
    name: `线路 ${id}`,
    provider: "responses-compatible",
    active_version_id: activeVersion.id,
    active_version: activeVersion,
    versions: draftVersion ? [draftVersion, activeVersion] : [activeVersion],
    models: [],
  };
}

const notify = vi.fn();

beforeEach(() => {
  for (const mock of Object.values(apiMock)) mock.mockReset();
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.configs.mockResolvedValue([connection("A"), connection("B")]);
  notify.mockReset();
});

afterEach(() => cleanup());

test.each(["success", "failure"])("保存草稿 %s 后恢复连接切换", async (outcome) => {
  const user = userEvent.setup();
  const pending = deferred();
  apiMock.createConfig.mockReturnValue(pending.promise);
  render(<ApiManagement notify={notify} />);

  await user.click(await screen.findByRole("button", { name: "编辑连接" }));
  await user.type(
    screen.getByRole("textbox", { name: "配置变更原因" }),
    "调整验证模型",
  );
  await user.click(screen.getByRole("button", { name: "保存草稿" }));

  await waitFor(() => expect(apiMock.createConfig).toHaveBeenCalledTimes(1));
  const otherConnection = screen.getByRole("button", { name: /线路 B/ });
  expect(otherConnection).toBeDisabled();
  expect(screen.getByRole("button", { name: "返回服务摘要" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "配置变更原因" })).toBeDisabled();

  await act(async () => {
    if (outcome === "success") {
      pending.resolve({
        ...connection("A").active_version,
        id: "A-version-2",
        version: 2,
      });
    } else {
      pending.reject(new Error("保存失败"));
    }
  });

  await waitFor(() => expect(otherConnection).toBeEnabled());
  if (outcome === "failure") {
    expect(screen.getByRole("textbox", { name: "配置变更原因" })).toHaveValue(
      "调整验证模型",
    );
    expect(notify).toHaveBeenCalledWith("保存失败", "error");
  }
  await user.click(otherConnection);
  expect(await screen.findByRole("heading", { name: "线路 B" })).toBeVisible();
  expect(screen.getByRole("textbox", { name: "接入名称" })).toHaveValue("线路 B");
});

test.each([
  ["发布版本", "publishConfig", "A-version-2"],
  ["确认放弃", "discardConfig", "A-version-2"],
  ["同步目录", "discoverModels", "A"],
])("%s 进行中锁定摘要页连接选择", async (action, apiMethod, targetId) => {
  const user = userEvent.setup();
  const pending = deferred();
  apiMock.configs.mockResolvedValue([connection("A", true), connection("B")]);
  apiMock[apiMethod].mockReturnValue(pending.promise);
  render(<ApiManagement notify={notify} />);

  const selector = await screen.findByRole("combobox", { name: "模型服务" });
  if (action === "确认放弃") {
    await user.click(screen.getByRole("button", { name: "放弃草稿" }));
  }
  await user.click(screen.getByRole("button", { name: action }));

  await waitFor(() => expect(apiMock[apiMethod]).toHaveBeenCalledWith(targetId));
  expect(selector).toBeDisabled();
  expect(selector).toHaveValue("A");
  expect(screen.getByRole("button", { name: "编辑连接" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "更多" }));
  expect(screen.getByRole("menuitem", { name: "新增模型服务" })).toBeDisabled();
  if (action === "确认放弃") {
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
  }

  await act(async () => pending.resolve({ count: 1 }));
  await waitFor(() => expect(selector).toBeEnabled());
  await user.selectOptions(selector, "B");
  expect(await screen.findByRole("heading", { name: "线路 B" })).toBeVisible();
});

test("保存模型期间锁定编辑弹窗与连接列表", async () => {
  const user = userEvent.setup();
  const pending = deferred();
  apiMock.createModel.mockReturnValue(pending.promise);
  render(<ApiManagement notify={notify} />);

  await user.click(await screen.findByRole("button", { name: "管理目录" }));
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(screen.getByRole("textbox", { name: /^模型 ID/ }), "new-model");
  await user.click(screen.getByRole("button", { name: "保存模型" }));

  await waitFor(() => expect(apiMock.createModel).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: /线路 B/ })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: /^模型 ID/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: "返回服务摘要" })).toBeDisabled();

  await act(async () => pending.reject(new Error("模型保存失败")));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /线路 B/ })).toBeEnabled(),
  );
  expect(screen.getByRole("textbox", { name: /^模型 ID/ })).toHaveValue("new-model");
  expect(notify).toHaveBeenCalledWith("模型保存失败", "error");
});

test("保存新草稿后保持选中新版本", async () => {
  const user = userEvent.setup();
  const original = connection("A", true);
  const saved = {
    ...original.versions[0],
    id: "A-version-3",
    version: 3,
    change_note: "更新验证模型",
  };
  apiMock.configs
    .mockResolvedValueOnce([original])
    .mockResolvedValueOnce([{ ...original, versions: [saved, ...original.versions] }]);
  apiMock.createConfig.mockResolvedValue(saved);
  render(<ApiManagement notify={notify} />);

  await user.click(await screen.findByRole("button", { name: "编辑连接" }));
  await user.type(
    screen.getByRole("textbox", { name: "配置变更原因" }),
    "更新验证模型",
  );
  await user.click(screen.getByRole("button", { name: "保存草稿" }));

  expect(await screen.findByText(/配置 #3 ·/)).toBeVisible();
  expect(screen.getByRole("textbox", { name: "配置变更原因" })).toHaveValue(
    "更新验证模型",
  );
});

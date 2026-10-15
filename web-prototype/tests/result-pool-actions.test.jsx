import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { ResultPoolActions } from "../src/features/classification-results/ResultPoolActions";
import { resultExportApi } from "../src/shared/api/resultExportApi";
import { changeDeliveryLifecycle } from "../src/shared/api/deliveryApi";

vi.mock("../src/shared/api/resultExportApi", () => ({
  resultExportApi: { create: vi.fn(), get: vi.fn(), save: vi.fn() },
}));
vi.mock("../src/shared/api/deliveryApi", () => ({ changeDeliveryLifecycle: vi.fn() }));

const result = {
  version_id: "result-synthetic",
  listing: "SYNTHETIC",
  revision: 3,
  publish_status: "published",
};

function setup(changes = {}) {
  const props = { result, onOpen: vi.fn(), onPrimary: vi.fn(), onChanged: vi.fn() };
  return { props, ...render(<ResultPoolActions {...props} {...changes} />) };
}

beforeEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
  changeDeliveryLifecycle.mockResolvedValue({ ok: true });
});
afterEach(cleanup);

test("当前结果按查看、下载、更多排列，创建看板收进菜单且支持键盘", async () => {
  const user = userEvent.setup();
  const { props, container } = setup();
  const cell = container.querySelector(".result-row-actions");
  expect([...cell.children].map((element) => element.tagName)).toEqual([
    "BUTTON",
    "SPAN",
    "DETAILS",
  ]);
  expect(screen.getByRole("button", { name: "创建分析看板" })).not.toBeVisible();
  await user.click(screen.getByRole("button", { name: "查看结果" }));
  expect(props.onOpen).toHaveBeenCalledOnce();
  const more = screen.getByLabelText("更多分类结果操作：SYNTHETIC");
  more.focus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("button", { name: "创建分析看板" })).toHaveFocus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("button", { name: "删除分类结果" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(more).toHaveFocus();
  expect(more).toHaveAttribute("aria-expanded", "false");
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("button", { name: "创建分析看板" }));
  expect(props.onPrimary).toHaveBeenCalledOnce();
  expect(more).toHaveAttribute("aria-expanded", "false");
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
});

test("删除沿用原确认和修订号校验，返回不会写入", async () => {
  const user = userEvent.setup();
  const { props } = setup();
  await user.click(screen.getByLabelText("更多分类结果操作：SYNTHETIC"));
  await user.click(screen.getByRole("button", { name: "删除分类结果" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("存在看板引用");
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "返回" }));
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
  await user.click(screen.getByLabelText("更多分类结果操作：SYNTHETIC"));
  await user.click(screen.getByRole("button", { name: "删除分类结果" }));
  await user.click(screen.getByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(props.onChanged).toHaveBeenCalledOnce());
  expect(changeDeliveryLifecycle).toHaveBeenCalledWith(
    "result",
    result.version_id,
    "delete",
    3,
  );
});

test("未发布结果仍可查看，创建看板保持禁用", async () => {
  setup({ result: { ...result, publish_status: "draft" } });
  expect(screen.getByRole("button", { name: "查看结果" })).toBeEnabled();
  await userEvent.click(screen.getByLabelText("更多分类结果操作：SYNTHETIC"));
  expect(screen.getByRole("button", { name: "创建分析看板" })).toBeDisabled();
});

test.each([
  ["queued", "正在生成"],
  ["failed", "重试下载"],
])("导出%s不影响查看和菜单，保留真实下载反馈", async (status, label) => {
  localStorage.setItem(`result-export:${result.version_id}`, "export-synthetic");
  resultExportApi.get.mockResolvedValue({
    id: "export-synthetic",
    status,
    error: status === "failed" ? "合成导出失败，请重试" : "",
  });
  setup();
  expect(await screen.findByRole("button", { name: label })).toHaveAttribute(
    "aria-busy",
    String(status === "queued"),
  );
  expect(screen.getByRole("button", { name: "查看结果" })).toBeEnabled();
  await userEvent.click(screen.getByLabelText("更多分类结果操作：SYNTHETIC"));
  expect(screen.getByRole("button", { name: "创建分析看板" })).toBeEnabled();
  if (status === "failed")
    expect(screen.getByRole("alert")).toHaveTextContent("合成导出失败");
  expect(resultExportApi.create).not.toHaveBeenCalled();
});

test("已删除结果提供查看、恢复及后端允许的下载，移除无效创建", async () => {
  const { props } = setup({
    result: { ...result, deleted_at: "2026-10-15T00:00:00Z" },
  });
  expect(screen.queryByRole("button", { name: "创建分析看板" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "查看结果" }));
  expect(props.onOpen).toHaveBeenCalledOnce();
  expect(props.onPrimary).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "下载" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "恢复分类结果" }));
  await waitFor(() =>
    expect(changeDeliveryLifecycle).toHaveBeenCalledWith(
      "result",
      result.version_id,
      "restore",
      3,
    ),
  );
});

test("已删除结果仍能下载，恢复失败保留当前记录并提示错误", async () => {
  const job = {
    id: "export-deleted-synthetic",
    status: "ready",
  };
  resultExportApi.create.mockResolvedValue(job);
  resultExportApi.get.mockResolvedValue(job);
  resultExportApi.save.mockResolvedValue(undefined);
  changeDeliveryLifecycle.mockRejectedValue(
    new Error("来源结果仍有冲突，请刷新后重试"),
  );
  const { props } = setup({
    result: { ...result, deleted_at: "2026-10-15T00:00:00Z" },
  });
  await userEvent.click(screen.getByRole("button", { name: "下载" }));
  await waitFor(() => expect(resultExportApi.save).toHaveBeenCalledWith(job));
  expect(resultExportApi.create).toHaveBeenCalledWith([result.version_id]);
  await userEvent.click(screen.getByRole("button", { name: "恢复分类结果" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("来源结果仍有冲突");
  expect(screen.getByRole("button", { name: "恢复分类结果" })).toBeEnabled();
  expect(props.onChanged).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "查看结果" })).toBeEnabled();
});

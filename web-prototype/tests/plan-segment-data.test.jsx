import { useState } from "react";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
const { preview } = vi.hoisted(() => ({ preview: vi.fn() }));
vi.mock("../src/shared/api/taskApi", () => ({
  taskApi: { previewTaskSegment: preview },
}));
import { ExecutionPlanSummary } from "../src/features/task-planning/ExecutionPlanSummary";
import { renderWithServerState as render } from "./renderWithServerState";
const segment = {
  segment_key: "key",
  scope: { listing: "DEMO", store: "合成店铺" },
  agent_family: "合成标准",
  status: "ready",
  record_count: 22,
  unique_comments: 21,
  variants: [],
};
const input = {
  dataset_version_id: "data",
  product_version_id: "products",
  config_version_id: "config",
  plan_hash: "a".repeat(64),
  store: null,
  listing: null,
};
function Harness() {
  const [keys, setKeys] = useState(["key"]);
  return (
    <ExecutionPlanSummary
      plan={{
        ...input,
        segments: [segment],
        record_count: 22,
        valid_comment_count: 22,
        unique_comment_count: 21,
        executable_count: 21,
        excluded_count: 0,
        blocked_count: 0,
        unknown_categories: [],
      }}
      previewInput={input}
      segmentSelection={{ keys, onChange: setKeys }}
    />
  );
}
beforeEach(() => {
  preview.mockReset();
});
afterEach(cleanup);
const response = {
  items: [{ group_no: 1, title: "合成标题", comment: "合成原文", record_count: 2 }],
  total: 21,
  record_total: 22,
  group_total: 21,
  page: 1,
  page_size: 20,
};

test("评论组翻页、源记录下钻和返回保留选择、筛选，关闭焦点返回入口", async () => {
  preview.mockImplementation(async (payload) =>
    payload.view === "records"
      ? {
          ...response,
          total: 2,
          items: [
            {
              ...response.items[0],
              source_row: 2,
              sku: "SKU",
              product_name: "合成产品",
              date: "2026-10-01",
              comment: " 合成原文 ",
            },
          ],
        }
      : response,
  );
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(screen.getByLabelText("搜索执行分组"), "DEMO");
  const trigger = screen.getByRole("button", { name: "查看数据" });
  await user.click(trigger);
  const dialog = await screen.findByRole("dialog", { name: "DEMO · 分组数据" });
  await within(dialog).findByText("合成原文");
  await user.click(within(dialog).getByRole("button", { name: "下一页" }));
  await waitFor(() =>
    expect(preview).toHaveBeenLastCalledWith(
      expect.objectContaining({
        segment_key: "key",
        plan_hash: input.plan_hash,
        page: 2,
      }),
    ),
  );
  await user.click(within(dialog).getByRole("button", { name: "查看 2 条源记录" }));
  await within(dialog).findByText("SKU · 合成产品");
  expect(preview).toHaveBeenLastCalledWith(
    expect.objectContaining({ view: "records", group_no: 1, page: 1 }),
  );
  await user.click(within(dialog).getByRole("button", { name: "评论组", exact: true }));
  await within(dialog).findByText("合成原文");
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(screen.getByLabelText("搜索执行分组")).toHaveValue("DEMO");
  expect(screen.getByRole("checkbox", { name: "选择 Listing：DEMO" })).toBeChecked();
});

test("读取失败可重试，关闭后迟到响应不覆盖新窗口", async () => {
  let resolve;
  preview
    .mockRejectedValueOnce(new Error("合成读取失败"))
    .mockResolvedValueOnce(response)
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockResolvedValue({
      ...response,
      items: [{ ...response.items[0], comment: "新窗口内容" }],
    });
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "查看数据" }));
  await screen.findByText("合成读取失败");
  await user.click(screen.getByRole("button", { name: "重试读取" }));
  await screen.findByText("合成原文");
  await user.click(screen.getByRole("button", { name: "全部源记录" }));
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "查看数据" }));
  await screen.findByText("新窗口内容");
  await act(async () => {
    resolve(response);
  });
  expect(screen.queryByText("合成原文")).not.toBeInTheDocument();
});

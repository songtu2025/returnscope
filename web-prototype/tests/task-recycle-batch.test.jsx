import { screen, within, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
import { mocks, item } from "./task-recycle-test-state";
import { TaskRecyclePage } from "../src/features/task-runtime/TaskRecyclePage";

const second = {
  ...item,
  id: "second",
  segment_key: "second-key",
  scope: { listing: "SECOND", store: "另一店铺" },
};
const third = {
  ...item,
  id: "third",
  segment_key: "third-key",
  scope: { listing: "THIRD", store: "合成站点" },
};
const items = [item, second, third];
const snapshot = (revision = 9) => ({
  id: item.task_id,
  revision,
  segments: items.map((row) => ({ ...row, status: "paused" })),
});
function setup() {
  mocks.request.mockResolvedValue({ items, total: 3 });
  mocks.task.mockResolvedValue(snapshot());
  mocks.control
    .mockResolvedValueOnce(snapshot(10))
    .mockResolvedValueOnce(snapshot(11))
    .mockResolvedValueOnce(snapshot(12));
  render(<TaskRecyclePage notify={vi.fn()} />);
}
async function selectAll() {
  await userEvent.click(
    await screen.findByRole("checkbox", { name: "选择当前页全部 3 条记录" }),
  );
}

test.each(["restore", "purge"])(
  "批量 %s 列出全部对象，取消无写入，确认后串行使用最新修订号",
  async (action) => {
    setup();
    await selectAll();
    const label = action === "restore" ? "恢复" : "永久删除";
    await userEvent.click(screen.getByRole("button", { name: `批量${label}` }));
    let dialog = within(screen.getByRole("dialog"));
    for (const row of items)
      expect(dialog.getByText(row.scope.listing, { exact: true })).toBeVisible();
    expect(dialog.getAllByText(item.task_id, { exact: true })).toHaveLength(3);
    await userEvent.click(dialog.getByRole("button", { name: "返回", exact: true }));
    expect(mocks.control).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: `批量${label}` }));
    dialog = within(screen.getByRole("dialog"));
    await userEvent.click(dialog.getByRole("button", { name: `确认${label} 3 条` }));
    await waitFor(() => expect(mocks.control).toHaveBeenCalledTimes(3));
    expect(
      mocks.control.mock.calls.map((call) => [call[2], call[3].expected_revision]),
    ).toEqual([
      [action, 9],
      [action, 10],
      [action, 11],
    ]);
    expect(
      await screen.findByRole("region", { name: "回收站操作结果" }),
    ).toHaveTextContent("已确认完成 3 条");
    expect(mocks.task).toHaveBeenCalledTimes(1);
  },
);

test("范围改变清空选择，当前页全选支持部分选中", async () => {
  setup();
  await userEvent.click(
    await screen.findByRole("checkbox", { name: /^选择 SYNTHETIC/ }),
  );
  expect(
    screen.getByRole("checkbox", { name: "选择当前页全部 3 条记录" }),
  ).toBePartiallyChecked();
  await userEvent.type(
    screen.getByRole("textbox", { name: "搜索回收站" }),
    "SECOND{Enter}",
  );
  expect(screen.getByRole("button", { name: "批量恢复" })).toBeDisabled();
});

test("第二项明确失败后停止，区分成功失败和未处理", async () => {
  setup();
  mocks.control
    .mockReset()
    .mockResolvedValueOnce(snapshot(10))
    .mockRejectedValueOnce(Object.assign(new Error("修订冲突"), { status: 409 }));
  await selectAll();
  await userEvent.click(screen.getByRole("button", { name: "批量恢复" }));
  await userEvent.click(screen.getByRole("button", { name: "确认恢复 3 条" }));
  const result = await screen.findByRole("region", { name: "回收站操作结果" });
  expect(result).toHaveTextContent("已确认完成 1 条 · 失败 1 条 · 未处理 1 条");
  await userEvent.click(within(result).getByText("查看逐项结果"));
  expect(result).toHaveTextContent("SECOND · 另一店铺");
  expect(result).toHaveTextContent("失败：修订冲突");
  expect(mocks.control).toHaveBeenCalledTimes(2);
});

test("提交响应丢失但只读核实已成功，不重发请求且余项停止", async () => {
  setup();
  mocks.control.mockReset().mockRejectedValueOnce(new Error("响应丢失"));
  mocks.task.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce({
    ...snapshot(10),
    segments: [{ ...item, deleted_at: null, status: "paused" }],
  });
  await selectAll();
  await userEvent.click(screen.getByRole("button", { name: "批量恢复" }));
  await userEvent.click(screen.getByRole("button", { name: "确认恢复 3 条" }));
  expect(
    await screen.findByRole("region", { name: "回收站操作结果" }),
  ).toHaveTextContent("已确认完成 1 条 · 失败 0 条 · 未处理 2 条");
  expect(mocks.control).toHaveBeenCalledTimes(1);
  expect(mocks.task).toHaveBeenCalledTimes(2);
});

test("核实失败保留阻断，只读核实未完成后才允许手动重新选择", async () => {
  setup();
  mocks.control.mockReset().mockRejectedValueOnce(new Error("响应丢失"));
  mocks.task
    .mockResolvedValueOnce(snapshot())
    .mockRejectedValueOnce(new Error("读取失败"))
    .mockResolvedValueOnce(snapshot());
  await selectAll();
  await userEvent.click(screen.getByRole("button", { name: "批量永久删除" }));
  const confirm = screen.getByRole("button", { name: "确认永久删除 3 条" });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  const verify = await screen.findByRole("button", { name: "刷新核实结果" });
  await waitFor(() => expect(verify).toBeEnabled());
  expect(screen.getByRole("button", { name: "批量永久删除" })).toBeDisabled();
  expect(
    screen.getByRole("checkbox", { name: "选择当前页全部 3 条记录" }),
  ).toBeDisabled();
  await userEvent.click(verify);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "刷新核实结果" }),
    ).not.toBeInTheDocument(),
  );
  expect(
    screen.getByRole("checkbox", { name: "选择当前页全部 3 条记录" }),
  ).toBeEnabled();
  expect(mocks.control).toHaveBeenCalledTimes(1);
});

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithServerState as render } from "./renderWithServerState";
import userEvent from "@testing-library/user-event";
import { api } from "../src/api";
import { GlobalSearch } from "../src/app/GlobalSearch";

vi.mock("../src/api", () => ({
  api: {
    tasks: vi.fn(),
    datasets: vi.fn(),
    searchClassificationFeedback: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.tasks).mockResolvedValue([
    { id: "synthetic-a", title: "合成任务甲", status: "done", owner_name: "合成用户" },
    { id: "synthetic-b", title: "合成任务乙", status: "done", owner_name: "合成用户" },
  ]);
  vi.mocked(api.datasets).mockResolvedValue([]);
  vi.mocked(api.searchClassificationFeedback).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

async function ready() {
  const onSelect = vi.fn();
  const onClose = vi.fn();
  render(<GlobalSearch onSelect={onSelect} onClose={onClose} />);
  const first = await screen.findByRole("button", { name: /合成任务甲/ });
  return {
    onSelect,
    onClose,
    first,
    input: screen.getByRole("textbox", { name: "全局搜索" }),
  };
}

describe("全局搜索输入法与键盘", () => {
  test("组合期间Enter和方向键用于输入，结束后Enter才打开结果", async () => {
    const { input, onSelect } = await ready();
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(onSelect).not.toHaveBeenCalled();
    expect(input).toHaveFocus();
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledExactlyOnceWith("analysis-tasks", {
      kind: "task",
      id: "synthetic-a",
    });
  });

  test.each([{ isComposing: true }, { keyCode: 229 }])(
    "原生输入法事件%s不触发打开",
    async (composition) => {
      const { input, onSelect } = await ready();
      fireEvent.keyDown(input, { key: "Enter", ...composition });
      expect(onSelect).not.toHaveBeenCalled();
      fireEvent.keyDown(input, { key: "Enter" });
      expect(onSelect).toHaveBeenCalledOnce();
    },
  );

  test("方向键选择第二条后Enter打开，Esc仍可关闭搜索", async () => {
    const { first, input, onSelect, onClose } = await ready();
    await userEvent.keyboard("{ArrowDown}");
    expect(first).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: /合成任务乙/ })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("analysis-tasks", {
      kind: "task",
      id: "synthetic-b",
    });
    input.focus();
    await userEvent.keyboard("{ArrowUp}");
    expect(screen.getByRole("button", { name: /合成任务乙/ })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});

test("同名任务显示标识和创建时间，粘贴任务 ID 可定位并打开", async () => {
  vi.mocked(api.tasks).mockResolvedValue([
    {
      id: "task-demo-first",
      title: "同名任务",
      created_at: "2026-10-01T00:00:00Z",
      status: "done",
      owner_name: "合成用户",
    },
    {
      id: "task-demo-second",
      title: "同名任务",
      created_at: "2026-10-02T00:00:00Z",
      status: "done",
      owner_name: "合成用户",
    },
  ]);
  const onSelect = vi.fn();
  render(<GlobalSearch onSelect={onSelect} onClose={vi.fn()} />);
  expect(
    await screen.findByRole("button", {
      name: /同名任务.*task-demo-first · 2026-10-01/,
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: /同名任务.*task-demo-second · 2026-10-02/ }),
  ).toBeVisible();
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "task-demo-second" } });
  expect(
    screen.queryByRole("button", { name: /task-demo-first/ }),
  ).not.toBeInTheDocument();
  expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(false);
  expect(onSelect).toHaveBeenCalledExactlyOnceWith("analysis-tasks", {
    kind: "task",
    id: "task-demo-second",
  });
});

test("同订单反馈显示不同结果标识，选择第二条进入对应版本", async () => {
  vi.mocked(api.searchClassificationFeedback).mockResolvedValue({
    items: ["first001", "second02"].map((version) => ({
      record: {
        id: version,
        result_version_id: `classification_version_${version}`,
        comment: "相同反馈",
        listing: "DEMO",
        store_site: "合成店铺",
        order_id: "DEMO-ORDER",
      },
    })),
  });
  const onSelect = vi.fn();
  render(<GlobalSearch onSelect={onSelect} onClose={vi.fn()} />);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "DEMO-ORDER" } });
  expect(
    await screen.findByRole("button", { name: /相同反馈.*结果 first001 · 合成店铺/ }),
  ).toBeVisible();
  expect(
    screen.getByTitle("结果版本 ID：classification_version_second02"),
  ).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: /相同反馈.*结果 second02 · 合成店铺/ }),
  );
  expect(onSelect).toHaveBeenCalledExactlyOnceWith("classification-results", {
    kind: "classification-result",
    id: "classification_version_second02",
    listing: "DEMO",
    orderId: "DEMO-ORDER",
  });
});

describe("全局搜索分类加载", () => {
  test("产品失败不影响已返回任务，独立重试不重拉任务", async () => {
    vi.mocked(api.datasets).mockRejectedValueOnce(new Error("合成产品失败"));
    const { input, onSelect } = await ready();
    await screen.findByText("产品信息读取失败");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("analysis-tasks", {
      kind: "task",
      id: "synthetic-a",
    });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByRole("button", { name: /合成任务甲/ })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "重试产品信息" }));
    await waitFor(() => expect(screen.queryByText("产品信息读取失败")).toBeNull());
    expect(api.tasks).toHaveBeenCalledOnce();
    expect(api.datasets).toHaveBeenCalledTimes(2);
    expect(api.searchClassificationFeedback).not.toHaveBeenCalled();
  });

  test("任务仍在等待时产品已可使用", async () => {
    vi.mocked(api.tasks).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.datasets).mockResolvedValue([
      {
        id: "synthetic-products",
        kind: "products",
        name: "合成产品",
        row_count: 1,
      },
    ]);
    const onSelect = vi.fn();
    render(<GlobalSearch onSelect={onSelect} onClose={vi.fn()} />);
    await screen.findByRole("button", { name: /合成产品/ });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("data-assets", {
      kind: "dataset",
      id: "synthetic-products",
      datasetKind: "products",
    });
  });

  test("任务失败仍展示产品，重试任务只请求任务", async () => {
    vi.mocked(api.tasks).mockRejectedValueOnce(new Error("合成任务失败"));
    vi.mocked(api.datasets).mockResolvedValue([
      {
        id: "synthetic-products",
        kind: "products",
        name: "合成产品",
        row_count: 1,
      },
    ]);
    render(<GlobalSearch onSelect={vi.fn()} onClose={vi.fn()} />);
    await screen.findByRole("button", { name: /合成产品/ });
    await screen.findByText("任务读取失败");
    await userEvent.click(screen.getByRole("button", { name: "重试任务" }));
    await screen.findByRole("button", { name: /合成任务甲/ });
    expect(api.tasks).toHaveBeenCalledTimes(2);
    expect(api.datasets).toHaveBeenCalledOnce();
  });

  test("工作区全部失败仍能搜索反馈，失败类别各自可重试", async () => {
    vi.mocked(api.tasks).mockRejectedValue(new Error("合成任务失败"));
    vi.mocked(api.datasets).mockRejectedValue(new Error("合成产品失败"));
    vi.mocked(api.searchClassificationFeedback).mockResolvedValue({
      items: [
        {
          record: {
            id: "synthetic-record",
            comment: "合成反馈",
            result_version_id: "synthetic-result",
          },
        },
      ],
    });
    const onSelect = vi.fn();
    render(<GlobalSearch onSelect={onSelect} onClose={vi.fn()} />);
    await screen.findByText("任务读取失败");
    await screen.findByText("产品信息读取失败");
    expect(screen.queryByText("没有找到匹配内容")).not.toBeInTheDocument();
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "合成反馈" } });
    await screen.findByRole("button", { name: /合成反馈/ });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("classification-results", {
      kind: "classification-result",
      id: "synthetic-result",
      listing: undefined,
      orderId: undefined,
    });
  });

  test("反馈失败只重试反馈，保留任务和输入", async () => {
    vi.mocked(api.searchClassificationFeedback).mockRejectedValueOnce(
      new Error("合成反馈失败"),
    );
    const { input } = await ready();
    fireEvent.change(input, { target: { value: "合成" } });
    await screen.findByText("反馈搜索失败");
    expect(screen.getByText("合成任务甲")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "重试反馈搜索" }));
    await waitFor(() => expect(screen.queryByText("反馈搜索失败")).toBeNull());
    expect(input).toHaveValue("合成");
    expect(api.tasks).toHaveBeenCalledOnce();
    expect(api.datasets).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(api.searchClassificationFeedback).toHaveBeenCalledTimes(2),
    );
  });

  test("查询更换后迟到反馈不覆盖新反馈，卸载终止当前搜索", async () => {
    let resolveOld;
    vi.mocked(api.searchClassificationFeedback).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    const view = render(<GlobalSearch onSelect={vi.fn()} onClose={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "旧查询" } });
    await waitFor(() =>
      expect(api.searchClassificationFeedback).toHaveBeenCalledOnce(),
    );
    const oldSignal = vi.mocked(api.searchClassificationFeedback).mock.calls[0][1]
      .signal;
    fireEvent.change(input, { target: { value: "新查询" } });
    await waitFor(() =>
      expect(api.searchClassificationFeedback).toHaveBeenCalledTimes(2),
    );
    const newSignal = vi.mocked(api.searchClassificationFeedback).mock.calls[1][1]
      .signal;
    expect(oldSignal.aborted).toBe(true);
    await act(async () =>
      resolveOld({
        items: [{ record: { id: "late", comment: "旧查询新查询迟到反馈" } }],
      }),
    );
    expect(screen.queryByText("旧查询新查询迟到反馈")).not.toBeInTheDocument();
    view.unmount();
    expect(newSignal.aborted).toBe(true);
  });
});

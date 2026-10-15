import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  render(<GlobalSearch onSelect={onSelect} onClose={onClose} notify={vi.fn()} />);
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

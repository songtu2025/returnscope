import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TaskIdentityCopy } from "../src/features/task-runtime/TaskIdentityCopy";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test.each([true, false])("复制完整任务 ID 并反馈结果：%s", async (success) => {
  const user = userEvent.setup();
  const clipboard = vi.spyOn(navigator.clipboard, "writeText");
  if (success) clipboard.mockResolvedValue();
  else clipboard.mockRejectedValue(new Error("拒绝剪贴板访问"));
  render(<TaskIdentityCopy id="task_synthetic_full_id" />);
  await user.click(
    screen.getByRole("button", { name: "复制任务 ID：task_synthetic_full_id" }),
  );
  expect(clipboard).toHaveBeenCalledWith("task_synthetic_full_id");
  expect(screen.getByRole("status")).toHaveTextContent(success ? "已复制" : "复制失败");
  expect(screen.getByText("task_synthetic_full_id")).toHaveAttribute(
    "title",
    "task_synthetic_full_id",
  );
});

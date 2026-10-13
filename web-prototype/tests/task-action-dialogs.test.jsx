import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import {
  SegmentCancelDialog,
  SegmentRetryDialog,
  TaskCancelDialog,
  TaskResumeDialog,
} from "../src/features/task-runtime/TaskActionDialogs";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(cleanup);

const task = {
  id: "synthetic-task",
  title: "合成任务",
  status: "paused",
  revision: 7,
};
const segment = {
  segment_key: "synthetic-segment",
  agent_family: "合成智能体",
  scope: { listing: "SYNTHETIC" },
};

const forms = [
  {
    Component: TaskCancelDialog,
    field: "取消原因",
    button: "确认取消任务",
    payload: { note: "合成原因", expected_revision: 7 },
  },
  {
    Component: TaskResumeDialog,
    field: "继续执行原因",
    button: "继续未完成片段",
    payload: { note: "合成原因", expected_revision: 7 },
  },
  {
    Component: SegmentCancelDialog,
    field: "取消原因",
    button: "确认取消 Listing",
    payload: "合成原因",
  },
  {
    Component: SegmentRetryDialog,
    field: "重试原因",
    button: "确认重试片段",
    payload: { reason: "合成原因", expected_revision: 7 },
  },
];

test.each(forms)(
  "$button 保留提交载荷，并在提交期间阻止重复操作",
  async ({ Component, field, button, payload }) => {
    const user = userEvent.setup();
    let resolveSave;
    const pending = new Promise((resolve) => {
      resolveSave = resolve;
    });
    const onSave = vi.fn(() => pending);
    const onClose = vi.fn();
    render(
      <Component
        task={task}
        segment={segment}
        error=""
        onSave={onSave}
        onClose={onClose}
      />,
    );
    await user.type(screen.getByLabelText(field), "合成原因");
    await user.click(screen.getByRole("button", { name: button }));
    expect(onSave).toHaveBeenCalledExactlyOnceWith(payload);
    const savingButton = screen.getByRole("button", { name: /正在(提交|保存)…/ });
    expect(savingButton).toBeDisabled();
    await user.click(savingButton);
    expect(onSave).toHaveBeenCalledOnce();
    resolveSave(false);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: button })).toBeEnabled(),
    );
    expect(screen.getByLabelText(field)).toHaveValue("合成原因");
    expect(onClose).not.toHaveBeenCalled();
  },
);

test("已取消任务恢复时显示重新排队原因，仍使用当前任务修订号", async () => {
  const onSave = vi.fn().mockResolvedValue(false);
  render(
    <TaskResumeDialog
      task={{ ...task, status: "cancelled" }}
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByRole("dialog", { name: "重新排队“合成任务”" })).toBeVisible();
  const button = screen.getByRole("button", { name: "重新排队未完成片段" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("重新排队原因"), "合成恢复原因");
  await userEvent.click(button);
  expect(onSave).toHaveBeenCalledExactlyOnceWith({
    note: "合成恢复原因",
    expected_revision: 7,
  });
});

test("片段重试错误留在表单，空白原因不能提交，取消只关闭弹窗", async () => {
  const onSave = vi.fn();
  const onClose = vi.fn();
  render(
    <SegmentRetryDialog
      task={task}
      segment={segment}
      error="合成版本冲突"
      onSave={onSave}
      onClose={onClose}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("合成版本冲突");
  await userEvent.type(screen.getByLabelText("重试原因"), "   ");
  expect(screen.getByRole("button", { name: "确认重试片段" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onClose).toHaveBeenCalledOnce();
  expect(onSave).not.toHaveBeenCalled();
});

test("失败项重试无需填写原因，自动保留审计载荷并阻止重复提交", async () => {
  const user = userEvent.setup();
  let finish;
  const onSave = vi.fn(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(
    <SegmentRetryDialog
      task={task}
      segment={{ ...segment, system_retry_available: true }}
      error=""
      onSave={onSave}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByRole("dialog", { name: "重试分析失败项？" })).toBeVisible();
  expect(screen.getByText("仅重试分析失败项，保留成功结果。")).toBeVisible();
  expect(screen.queryByLabelText("重试原因")).not.toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "开始重试" });
  expect(submit).toBeEnabled();
  await user.click(submit);
  expect(onSave).toHaveBeenCalledExactlyOnceWith({
    expected_revision: 7,
    reason: "重试分析失败项",
  });
  const pending = screen.getByRole("button", { name: "正在提交…" });
  expect(pending).toBeDisabled();
  await user.click(pending);
  expect(onSave).toHaveBeenCalledOnce();
  finish(false);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "开始重试" })).toBeEnabled(),
  );
});

test("失败项重试显示错误，取消确认不提交", async () => {
  const onSave = vi.fn();
  const onClose = vi.fn();
  render(
    <SegmentRetryDialog
      task={task}
      segment={{ ...segment, system_retry_available: true }}
      error="合成版本冲突，请刷新后重试"
      onSave={onSave}
      onClose={onClose}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("合成版本冲突，请刷新后重试");
  expect(screen.queryByLabelText("重试原因")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onClose).toHaveBeenCalledOnce();
  expect(onSave).not.toHaveBeenCalled();
});

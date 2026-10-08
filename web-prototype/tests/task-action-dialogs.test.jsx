import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import {
  SegmentCancelDialog,
  SegmentRetryDialog,
  TaskCancelDialog,
  TaskRenameDialog,
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
    Component: TaskRenameDialog,
    field: "修改原因",
    button: "保存修改",
    payload: { title: "合成任务", note: "合成原因", expected_revision: 7 },
  },
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

test("修改名称保留独立名称与原因输入，并只提交修订号", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(false);
  render(<TaskRenameDialog task={task} onSave={onSave} onClose={vi.fn()} />);
  const title = screen.getByLabelText("任务名称");
  await user.clear(title);
  await user.type(title, "合成新任务");
  await user.type(screen.getByLabelText("修改原因"), "合成更名原因");
  await user.click(screen.getByRole("button", { name: "保存修改" }));
  expect(onSave).toHaveBeenCalledExactlyOnceWith({
    title: "合成新任务",
    note: "合成更名原因",
    expected_revision: 7,
  });
  expect(title).toHaveValue("合成新任务");
  expect(screen.getByLabelText("修改原因")).toHaveValue("合成更名原因");
});

test("更名弹窗限制焦点，未保存关闭需确认，关闭后回到入口", async () => {
  function Workspace() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>更名入口</button>
        {open && (
          <TaskRenameDialog
            task={task}
            onSave={vi.fn()}
            onClose={() => setOpen(false)}
          />
        )}
      </>
    );
  }
  const user = userEvent.setup();
  render(<Workspace />);
  const trigger = screen.getByRole("button", { name: "更名入口" });
  await user.click(trigger);
  expect(screen.getByLabelText("任务名称")).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByRole("button", { name: "关闭" })).toHaveFocus();
  await user.tab({ shift: true });
  expect(screen.getByRole("button", { name: "保存修改" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  await user.click(trigger);
  await user.type(screen.getByLabelText("修改原因"), "合成草稿");
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "继续编辑" })).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("修改原因")).toHaveValue("合成草稿");
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "放弃修改并关闭" }));
  expect(trigger).toHaveFocus();
});

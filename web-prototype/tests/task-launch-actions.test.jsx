import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { TaskLaunchActions } from "../src/features/task-create/NewTaskActions";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => cleanup());

function actions(changes = {}) {
  return {
    prepared: false,
    dataEntryMode: "mysql",
    mysqlState: { busy: "", ready: false, rowCount: 0 },
    selectedReturns: undefined,
    submitting: false,
    canContinue: true,
    launchStatus: "合成计划状态",
    submitError: "",
    submitLabel: "合成开始分析",
    onSubmit: vi.fn(),
    onPrepareExisting: vi.fn(),
    ...changes,
  };
}

test.each([
  [{}, "选择店铺和日期，查看本次分析范围", "准备分析", true],
  [
    { mysqlState: { busy: "import", ready: true, rowCount: 4 } },
    "正在保存本次数据…",
    "正在准备…",
    true,
  ],
  [
    { mysqlState: { busy: "preview", ready: true, rowCount: 4 } },
    "已选 4 条用户反馈",
    "准备分析",
    true,
  ],
  [
    { mysqlState: { busy: "", ready: true, rowCount: 0 } },
    "已选 0 条用户反馈",
    "准备分析",
    false,
  ],
  [{ dataEntryMode: "existing" }, "请选择本次分析数据", "准备分析", true],
  [
    { dataEntryMode: "upload", selectedReturns: { row_count: 0 } },
    "已选 0 条用户反馈",
    "准备分析",
    false,
  ],
  [{ prepared: true }, "合成计划状态", "合成开始分析", false],
  [
    { prepared: true, submitting: true, submitError: "合成错误" },
    "合成计划状态",
    "正在创建…",
    true,
  ],
  [{ prepared: true, submitError: "合成错误" }, "合成计划状态", "重试创建", false],
  [{ prepared: true, canContinue: false }, "合成计划状态", "合成开始分析", true],
])("启动状态、优先级与按钮可用性保持：%s", (changes, status, label, disabled) => {
  render(<TaskLaunchActions {...actions(changes)} />);
  expect(screen.getByRole("status")).toHaveTextContent(status);
  const button = screen.getByRole("button", { name: label });
  expect(button.disabled).toBe(disabled);
});

test("数据库准备按钮仍提交原表单，已有数据和正式创建使用各自回调", async () => {
  const user = userEvent.setup();
  const onFormSubmit = vi.fn((event) => event.preventDefault());
  const props = actions({ mysqlState: { busy: "", ready: true, rowCount: 3 } });
  const view = render(
    <>
      <form id="mysql-prepare-form" onSubmit={onFormSubmit} />
      <TaskLaunchActions {...props} />
    </>,
  );
  const button = screen.getByRole("button", { name: "准备分析" });
  expect(button).toHaveAttribute("form", "mysql-prepare-form");
  expect(button).toHaveAttribute("type", "submit");
  await user.click(button);
  expect(onFormSubmit).toHaveBeenCalledOnce();
  expect(props.onPrepareExisting).not.toHaveBeenCalled();
  view.rerender(
    <TaskLaunchActions
      {...props}
      dataEntryMode="existing"
      selectedReturns={{ row_count: 3 }}
    />,
  );
  await user.click(screen.getByRole("button", { name: "准备分析" }));
  expect(props.onPrepareExisting).toHaveBeenCalledOnce();
  expect(props.onSubmit).not.toHaveBeenCalled();
  view.rerender(<TaskLaunchActions {...props} prepared />);
  const submit = screen.getByRole("button", { name: "合成开始分析" });
  expect(submit).toHaveAttribute("aria-describedby", "task-action-status");
  await user.click(submit);
  expect(props.onSubmit).toHaveBeenCalledOnce();
});

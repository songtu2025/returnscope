import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { TaskLaunchActions } from "../src/features/task-create/NewTaskActions";
import { TaskPlanReviewStep } from "../src/features/task-create/TaskPlanReviewStep";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => cleanup());

test("重新检查时焦点留在计划区域，完成后不会落回页面根节点", async () => {
  const props = {
    preflight: { status: "error", data: null, error: "合成计划过期" },
    onRetryPreflight: vi.fn(),
    categoryCompletionRequired: false,
    blocked: false,
    countMismatch: false,
    noExecutable: false,
    partialPlan: false,
    planCounts: { executable: 0, notAnalyzed: 0 },
    dataQuality: null,
    unresolvedPolicy: "block_all",
    onPolicyChange: vi.fn(),
    onResolveCategories: vi.fn(),
    segmentOrder: [],
    onSegmentOrderChange: vi.fn(),
    requiresScopeConfirmation: false,
    scopeConfirmed: false,
    onScopeConfirmationChange: vi.fn(),
  };
  const view = render(<TaskPlanReviewStep {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "重新检查" }));
  const workspace = view.container.querySelector(".task-plan-workspace");
  expect(workspace).toHaveFocus();
  expect(props.onRetryPreflight).toHaveBeenCalledOnce();
  view.rerender(
    <TaskPlanReviewStep
      {...props}
      preflight={{ status: "loading", data: null, error: "" }}
    />,
  );
  expect(workspace).toHaveFocus();
  view.rerender(
    <TaskPlanReviewStep
      {...props}
      preflight={{ status: "idle", data: null, error: "" }}
    />,
  );
  expect(workspace).toHaveFocus();
});

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

test("数据库准备提交表单，正式创建使用提交回调", async () => {
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
  view.rerender(<TaskLaunchActions {...props} prepared />);
  const submit = screen.getByRole("button", { name: "合成开始分析" });
  expect(submit).toHaveAttribute("aria-describedby", "task-action-status");
  await user.click(submit);
  expect(props.onSubmit).toHaveBeenCalledOnce();
  expect(screen.getByRole("status")).toHaveFocus();
  view.rerender(
    <TaskLaunchActions {...props} prepared submitting canContinue={false} />,
  );
  expect(screen.getByRole("status")).toHaveFocus();
  view.rerender(<TaskLaunchActions {...props} prepared submitError="合成创建失败" />);
  expect(screen.getByRole("status")).toHaveFocus();
  expect(screen.getByRole("button", { name: "重试创建" })).toBeEnabled();
});

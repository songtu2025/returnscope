import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { useDismissibleDetails } from "../src/hooks/useDismissibleDetails";
import { TaskRegistryRow } from "../src/features/task-runtime/TaskRegistryRow";
import { TaskDetailHeader } from "../src/features/task-runtime/TaskDetailHeader";
import { StandardWorkspaceHeader } from "../src/features/classification-standards/StandardWorkspaceHeader";
import { LabelWorkspaceHeader } from "../src/features/classification-standards/LabelWorkspaceHeader";
import { ModelServiceRuntimeSummary } from "../src/features/system-settings/ModelServiceRuntimeSummary";
import { TaskRegistryFilters } from "../src/features/task-runtime/TaskRegistryFilters";
import { SegmentBoardToolbar } from "../src/features/task-runtime/SegmentBoardToolbar";
import { MysqlReturnFilters } from "../src/features/task-create/MysqlReturnFilters";

afterEach(cleanup);

function Fixture({ menu = true, disabled = false, onAction = () => {} }) {
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu, disabled });
  const [value, setValue] = useState("");
  return (
    <details {...detailsProps}>
      <summary {...summaryProps}>合成入口</summary>
      <button type="button" onClick={onAction}>
        首项
      </button>
      <button type="button" disabled onClick={onAction}>
        禁用项
      </button>
      <button type="button" onClick={onAction}>
        末项
      </button>
      {!menu && (
        <input
          aria-label="合成条件"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      )}
    </details>
  );
}

function mount(view) {
  return render(
    <>
      <style>{"details:not([open]) > :not(summary) { display: none; }"}</style>
      {view}
      <button type="button">外部操作</button>
    </>,
  );
}

const task = {
  id: "SYNTHETIC",
  title: "合成任务",
  status: "completed",
  created_at: "2026-10-09",
  owner_name: "合成人员",
};
const menus = [
  [
    "任务列表",
    (action) => <TaskRegistryRow task={task} selectable onCreateSimilar={action} />,
    "更多任务操作：合成任务",
    "创建类似任务",
  ],
  [
    "任务详情",
    (action) => (
      <TaskDetailHeader
        task={task}
        summary={{ statusLabel: "已完成", generated: 0 }}
        onOpenRename={action}
      />
    ),
    "更多任务操作",
    "修改名称",
  ],
  [
    "分类标准",
    (action) => (
      <StandardWorkspaceHeader
        detail={{ name: "合成标准", status: "active", version_no: 1 }}
        onDelete={action}
      />
    ),
    "更多",
    "停用标准",
  ],
  [
    "标签工作台",
    (action) => (
      <LabelWorkspaceHeader
        label={{ name: "合成标签", code: "SYNTHETIC" }}
        editable
        published
        content={{ labels: [{}, {}] }}
        setPending={action}
      />
    ),
    "更多",
    "停用标签",
  ],
  [
    "模型服务",
    (action) => (
      <ModelServiceRuntimeSummary
        selectedConnection={{ name: "合成连接" }}
        onEditLimits={action}
        availableModelCount={0}
      />
    ),
    "更多",
    "请求限制",
  ],
];

test.each(menus)(
  "%s：关闭、互斥和选中后执行原动作",
  async (_name, view, triggerName, actionName) => {
    const action = vi.fn();
    mount(
      <>
        <div>{view(action)}</div>
        <Fixture />
      </>,
    );
    const summary =
      screen.queryByLabelText(triggerName) ??
      screen.getByText(triggerName, { selector: "summary", exact: true });
    await userEvent.click(summary);
    expect(summary).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByText("外部操作"));
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(summary);
    summary.focus();
    await userEvent.keyboard("{Escape}");
    expect(summary).toHaveFocus();
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(summary);
    fireEvent.focus(screen.getByText("外部操作"));
    fireEvent.blur(summary, { relatedTarget: screen.getByText("外部操作") });
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(summary);
    await userEvent.click(screen.getByText("合成入口"));
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(summary);
    await userEvent.click(screen.getByText(actionName));
    expect(action).toHaveBeenCalledOnce();
    expect(summary).toHaveAttribute("aria-expanded", "false");
  },
);

test("键盘打开菜单，方向键、首尾键跳过禁用项，Enter只执行一次", async () => {
  const action = vi.fn();
  mount(<Fixture onAction={action} />);
  const user = userEvent.setup();
  screen.getByText("合成入口").focus();
  await user.keyboard("{ArrowUp}");
  expect(screen.getByText("末项")).toHaveFocus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByText("首项")).toHaveFocus();
  await user.keyboard("{End}{Home}{ArrowDown}");
  expect(screen.getByText("末项")).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(action).toHaveBeenCalledOnce();
  await user.keyboard(" ");
  expect(screen.getByText("首项")).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.getByText("合成入口")).toHaveFocus();
});

test("Tab自然离开，外部点击不抢焦点，控件持续调整保留值", async () => {
  mount(<Fixture menu={false} />);
  const user = userEvent.setup();
  const summary = screen.getByText("合成入口");
  await user.click(summary);
  await user.type(screen.getByLabelText("合成条件"), "合成值");
  expect(summary).toHaveAttribute("aria-expanded", "true");
  await user.tab();
  expect(summary).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByText("外部操作")).toHaveFocus();
  await user.click(summary);
  expect(screen.getByLabelText("合成条件")).toHaveValue("合成值");
  await user.click(screen.getByText("外部操作"));
  expect(screen.getByText("外部操作")).toHaveFocus();
});

test("禁用入口不展开，禁用操作不执行，菜单Esc不传播至父弹窗", async () => {
  const parentKey = vi.fn();
  const action = vi.fn();
  const { rerender } = mount(<Fixture disabled />);
  await userEvent.click(screen.getByText("合成入口"));
  expect(screen.getByText("合成入口")).toHaveAttribute("aria-expanded", "false");
  rerender(<Fixture onAction={action} />);
  await userEvent.click(screen.getByText("合成入口"));
  await userEvent.click(screen.getByText("禁用项"));
  expect(action).not.toHaveBeenCalled();
  if (screen.getByText("合成入口").getAttribute("aria-expanded") === "false") {
    await userEvent.click(screen.getByText("合成入口"));
  }
  screen.getByText("首项").focus();
  document.addEventListener("keydown", parentKey);
  await userEvent.keyboard("{Escape}");
  document.removeEventListener("keydown", parentKey);
  expect(parentKey).not.toHaveBeenCalled();
});

test("卸载后清除外部监听，不影响下一次打开", async () => {
  const { unmount } = mount(<Fixture />);
  await userEvent.click(screen.getByText("合成入口"));
  unmount();
  mount(<Fixture />);
  await userEvent.click(screen.getByText("合成入口"));
  expect(screen.getByText("合成入口")).toHaveAttribute("aria-expanded", "true");
});

function Settings({ onParallelism }) {
  const [value, setValue] = useState(2);
  return (
    <SegmentBoardToolbar
      task={task}
      query=""
      statusFilter="all"
      parallelism={{
        changingParallelism: false,
        setChangingParallelism: () => {},
        canManageQueue: true,
        maxParallelSegments: value,
        ownerRunningSegments: 0,
        onParallelism: async (next) => {
          setValue(next);
          await onParallelism(next);
        },
      }}
    />
  );
}

test("实际筛选与执行设置调整后保持展开，不重复调用", async () => {
  const change = vi.fn();
  const parallel = vi.fn().mockResolvedValue(undefined);
  mount(
    <>
      <TaskRegistryFilters
        viewState={{ owner: "all", sort: "updated_desc", filter: "all", query: "" }}
        owners={["合成人员"]}
        counts={{}}
        searchInputRef={{ current: null }}
        onViewStateChange={change}
      />
      <Settings onParallelism={parallel} />
    </>,
  );
  await userEvent.click(screen.getByText("筛选与排序"));
  await userEvent.selectOptions(screen.getByLabelText("按负责人筛选"), "合成人员");
  expect(change).toHaveBeenCalledExactlyOnceWith({ owner: "合成人员" });
  expect(screen.getByText("筛选与排序")).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(screen.getByText("执行设置"));
  expect(screen.getByText("筛选与排序")).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(screen.getByLabelText("增加 Listing 并行数"));
  expect(parallel).toHaveBeenCalledExactlyOnceWith(3);
  const increase = screen.getByLabelText("增加 Listing 并行数");
  expect(increase).toBeDisabled();
  // jsdom 不会自动产生浏览器禁用焦点按钮时的失焦事件。
  fireEvent.blur(increase, { relatedTarget: null });
  expect(screen.getByText("执行设置")).toHaveFocus();
  expect(screen.getByText("执行设置")).toHaveAttribute("aria-expanded", "true");
});

test("日期手工输入保持展开，完成与预设关闭，SKU保留已有关闭行为", async () => {
  const update = vi.fn();
  mount(
    <MysqlReturnFilters
      schema={{ stores: [] }}
      form={{ store: "", sku: "", date_from: "", date_to: "" }}
      update={update}
    />,
  );
  const date = screen.getByText("反馈日期", { exact: false, selector: "summary" });
  await userEvent.click(date);
  fireEvent.change(screen.getByLabelText("开始日期"), {
    target: { value: "2026-10-01" },
  });
  expect(update).toHaveBeenCalledExactlyOnceWith({ date_from: "2026-10-01" });
  expect(date).toHaveAttribute("aria-expanded", "true");
  await userEvent.click(screen.getByText("完成"));
  expect(date).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(date);
  await userEvent.click(screen.getByRole("button", { name: "近30天" }));
  expect(date).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(date);
  await userEvent.click(screen.getByTitle("指定商品"));
  expect(date).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByLabelText("SKU / MSKU（精确匹配）")).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.getByTitle("指定商品")).toHaveFocus();
});

import { act, cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TaskRegistry } from "../src/features/task-runtime/TaskRegistry";
import { DashboardSelectionBar } from "../src/features/classification-results/ClassificationResultListParts";
import { useResultSelection } from "../src/features/classification-results/useResultSelection";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import {
  createDashboardSelection,
  readDashboardSelection,
} from "../src/features/analysis-dashboards/dashboardSelectionStorage";
import { renderWithServerState as render } from "./renderWithServerState";

const tasks = ["one", "two"].map((id) => ({
  id,
  title: "同名任务",
  status: "completed",
  owner_name: id,
  segments: [],
  progress_percent: 100,
  progress_current: 1,
  progress_total: 1,
}));
const state = {
  filter: "all",
  query: "",
  owner: "all",
  sort: "updated_desc",
  attentionOnly: false,
};
const taskProps = {
  tasks,
  selectedId: null,
  viewState: state,
  onViewStateChange: vi.fn(),
  loading: false,
  error: "",
  hasData: true,
  onReload: vi.fn(),
  onCreate: vi.fn(),
  onOpen: vi.fn(),
  onArchive: vi.fn().mockResolvedValue(false),
  onCreateSimilar: vi.fn(),
};
beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});
afterEach(cleanup);

test("任务筛选后明确范围，执行仅包含当前可见选中项，筛选外可逐项取消", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<TaskRegistry {...taskProps} />);
  await user.click(
    screen.getByRole("checkbox", { name: "选择当前列表中的可管理任务" }),
  );
  rerender(<TaskRegistry {...taskProps} viewState={{ ...state, owner: "one" }} />);
  const bar = screen.getByRole("region", { name: "批量任务操作" });
  expect(bar).toHaveTextContent("已选择 2 个任务");
  expect(bar).toHaveTextContent(
    "当前列表可操作 1 个 · 当前不可操作 0 个 · 筛选外 1 个",
  );
  await user.click(within(bar).getByRole("button", { name: "归档当前列表 1 项" }));
  expect(taskProps.onArchive).toHaveBeenCalledExactlyOnceWith(["one"], true);
  await user.click(within(bar).getByText("查看已选任务"));
  expect(within(bar).getByText("two", { selector: "code" })).toBeVisible();
  await user.click(within(bar).getByRole("button", { name: "取消选择任务 two" }));
  expect(bar).toHaveTextContent("已选择 1 个任务");
  expect(bar).toHaveTextContent("筛选外 0 个");
});

test("任务全在筛选外时仍可查看和取消，批量按钮不可执行", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<TaskRegistry {...taskProps} />);
  await user.click(
    screen.getByRole("checkbox", { name: "选择当前列表中的可管理任务" }),
  );
  rerender(<TaskRegistry {...taskProps} viewState={{ ...state, query: "不存在" }} />);
  const bar = screen.getByRole("region", { name: "批量任务操作" });
  expect(bar).toHaveTextContent(
    "当前列表可操作 0 个 · 当前不可操作 0 个 · 筛选外 2 个",
  );
  expect(within(bar).getByRole("button", { name: "归档当前列表 0 项" })).toBeDisabled();
  await user.click(within(bar).getByRole("button", { name: "取消选择", exact: true }));
  expect(
    screen.queryByRole("region", { name: "批量任务操作" }),
  ).not.toBeInTheDocument();
});

const selected = ["version-one", "version-two"].map((id) => ({
  result_version_id: id,
  listing: "同名Listing",
  store_site: "TEST:US",
  record_count: 2,
  unit_count: 1,
}));
function ResultHarness({ token, pageIds = ["version-two"], loading = false }) {
  const route = classificationResultRouteState({ selection_token: token, page: "2" });
  const selection = useResultSelection({ route, updateRoute: vi.fn(), userId: "user" });
  return (
    <>
      <DashboardSelectionBar
        selected={selection.selectedResults}
        currentPageIds={new Set(pageIds)}
        loading={loading}
        onClear={selection.clearSelection}
        onRemove={selection.removeSelection}
      />
      <button onClick={selection.continueToDashboard}>创建</button>
    </>
  );
}

test("结果选择明确跨页范围，逐项移除同步存储且保留原创建草稿", async () => {
  const token = createDashboardSelection("user", {
    selected,
    dashboard_form: { name: "已填草稿" },
    resolved_result_version_ids: ["旧决议"],
  });
  const user = userEvent.setup();
  render(<ResultHarness token={token} />);
  expect(screen.getByText("当前页 1 个 · 其他页或筛选外 1 个")).toBeVisible();
  expect(screen.getByText("创建时包含全部已选结果")).toBeVisible();
  await user.click(screen.getByText("查看已选结果"));
  expect(screen.getByText("version-one", { selector: "code" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "取消选择结果 version-one" }));
  expect(screen.getByText("已选 1 个结果版本")).toBeVisible();
  expect(readDashboardSelection("user", token)).toMatchObject({
    selected: [selected[1]],
    resolved_result_version_ids: [],
    dashboard_form: { name: "已填草稿" },
  });
  await user.click(screen.getByRole("button", { name: "创建", exact: true }));
  expect(window.location.hash).toContain("#analysis-dashboards?");
  expect(readDashboardSelection("user", token).selected).toEqual([selected[1]]);
});

test("结果加载中不使用旧页数据冒充当前页数量，完成后重算且支持清空", async () => {
  const token = createDashboardSelection("user", { selected });
  const { rerender } = render(<ResultHarness token={token} loading />);
  expect(screen.getByText("当前页统计更新中")).toBeVisible();
  expect(screen.queryByText(/当前页 1 个/)).not.toBeInTheDocument();
  rerender(<ResultHarness token={token} pageIds={[]} />);
  expect(screen.getByText("当前页 0 个 · 其他页或筛选外 2 个")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "清空" }));
  expect(readDashboardSelection("user", token).selected).toEqual([]);
});

test("结果跨页选择保持全部创建范围，不额外读取记录", async () => {
  const token = createDashboardSelection("user", { selected });
  render(<ResultHarness token={token} />);
  await act(async () =>
    userEvent.click(screen.getByRole("button", { name: "创建", exact: true })),
  );
  expect(readDashboardSelection("user", token).selected).toEqual(selected);
});

test("已选任务变为运行中时属于当前不可操作，不冒充筛选外", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<TaskRegistry {...taskProps} />);
  await user.click(
    screen.getByRole("checkbox", { name: "选择当前列表中的可管理任务" }),
  );
  rerender(
    <TaskRegistry
      {...taskProps}
      tasks={tasks.map((task) => ({ ...task, status: "running" }))}
    />,
  );
  const bar = screen.getByRole("region", { name: "批量任务操作" });
  expect(bar).toHaveTextContent(
    "当前列表可操作 0 个 · 当前不可操作 2 个 · 筛选外 0 个",
  );
  expect(within(bar).getByRole("button", { name: "归档当前列表 0 项" })).toBeDisabled();
  await user.click(within(bar).getByText("查看已选任务"));
  expect(within(bar).getAllByText("当前列表不可操作")).toHaveLength(2);
});

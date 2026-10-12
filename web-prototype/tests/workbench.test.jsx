import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { summary } = vi.hoisted(() => ({ summary: vi.fn() }));

vi.mock("../src/shared/api/workbenchApi", () => ({ workbenchApi: { summary } }));

import { WorkbenchPage } from "../src/features/workbench/WorkbenchPage";
import { renderWithServerState as render } from "./renderWithServerState";

beforeEach(() => {
  summary.mockReset();
  window.location.hash = "";
});

afterEach(() => cleanup());

test("首页慢请求只显示一个加载提示，两个卡片不重复加载或提前显示空态", async () => {
  let finish;
  summary.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<WorkbenchPage onNavigate={vi.fn()} />);
  await waitFor(() =>
    expect(document.querySelectorAll(".inline-loading.ant-spin-spinning")).toHaveLength(
      1,
    ),
  );
  expect(document.querySelectorAll(".workbench-card .inline-loading")).toHaveLength(0);
  expect(document.querySelector(".workbench-grid")).toHaveAttribute(
    "aria-busy",
    "true",
  );
  expect(screen.queryByText("当前没有待处理事项或后台任务")).toBeNull();
  expect(screen.queryByText("还没有可查看的产出")).toBeNull();
  expect(summary).toHaveBeenCalledTimes(1);
  await act(async () => finish({ actions: [], recent_outputs: [], counts: {} }));
  expect(await screen.findByText("还没有可查看的产出")).toBeVisible();
  expect(document.querySelectorAll(".inline-loading.ant-spin-spinning")).toHaveLength(
    0,
  );
});

test("工作台只调用一次真实汇总并按具体目标跳转", async () => {
  summary.mockResolvedValue({
    actions: [
      {
        type: "blocked",
        status: "blocked",
        object_type: "task",
        object_id: "task-1",
        title: "商品信息待补充",
        reason: "缺失品类",
        actor: { name: "系统管理员" },
        updated_at: "2026-08-12T09:00:00Z",
        target: { route: "tasks", task_id: "task-1", segment_id: "segment-1" },
      },
    ],
    recent_outputs: [
      {
        type: "classification_result",
        version_id: "result-1",
        version_no: 1,
        title: "SR001 分类结果",
        updated_at: "2026-08-12T09:10:00Z",
        target: { route: "classification-results", result_version_id: "result-1" },
      },
    ],
    counts: { blocked: 1 },
  });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  expect(await screen.findByText("商品信息待补充")).toBeVisible();
  expect(screen.getByText("SR001 分类结果")).toBeVisible();
  expect(summary).toHaveBeenCalledTimes(1);
  expect(summary).toHaveBeenCalledWith(5);
  expect(document.querySelectorAll(".inline-loading.ant-spin-spinning")).toHaveLength(
    0,
  );
  expect(screen.queryByText("我的运行额度")).not.toBeInTheDocument();

  await userEvent.click(screen.getByText("商品信息待补充"));
  expect(window.location.hash).toBe(
    "#analysis-tasks?task_id=task-1&segment_id=segment-1",
  );

  await userEvent.click(screen.getByText("SR001 分类结果"));
  expect(window.location.hash).toBe(
    "#classification-results?result_version_id=result-1",
  );
});

test("需复核待办直接进入待复核反馈，不进入批次或修改历史", async () => {
  summary.mockResolvedValue({
    actions: [
      {
        type: "review_required",
        status: "review_required",
        object_type: "classification_result",
        object_id: "result-review-1",
        title: "SR002 分类结果",
        reason: "分类结果需要人工复核",
        actor: { name: "系统管理员" },
        updated_at: "2026-08-12T09:00:00Z",
        target: {
          route: "classification-results",
          result_version_id: "result-review-1",
          task_id: "task-review-1",
          segment_id: "segment-review-1",
          action: "review",
          tab: "history",
        },
      },
    ],
    recent_outputs: [],
    counts: { review_required: 1 },
  });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  const action = await screen.findByRole("button", {
    name: /SR002 分类结果.*处理待复核记录/,
  });
  expect(screen.queryByText("创建复核批次")).not.toBeInTheDocument();
  action.focus();
  await userEvent.keyboard("{Enter}");

  expect(window.location.hash).toBe(
    "#classification-results?task_id=task-review-1&segment_id=segment-review-1&result_version_id=result-review-1&record_quality_status=review_required",
  );
});

test("原子汇总失败只显示一个共享错误和一次重试", async () => {
  summary
    .mockRejectedValueOnce(new Error("工作台接口不可用"))
    .mockResolvedValueOnce({ actions: [], recent_outputs: [], counts: {} });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText("首页数据读取失败")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "重新加载" })).toHaveLength(1);

  screen.getByRole("button", { name: "重新加载" }).focus();
  await userEvent.keyboard("{Enter}");
  expect(await screen.findByText("当前没有待处理事项或后台任务")).toBeVisible();
  expect(screen.getByText("还没有可查看的产出")).toBeVisible();
  expect(summary).toHaveBeenCalledTimes(2);
});

test("工作台无数据展示真实空态且快捷入口可用", async () => {
  const onNavigate = vi.fn();
  summary.mockResolvedValue({ actions: [], recent_outputs: [], counts: {} });

  render(<WorkbenchPage onNavigate={onNavigate} />);

  expect(await screen.findByText("当前没有待处理事项或后台任务")).toBeVisible();
  expect(screen.getByText("还没有可查看的产出")).toBeVisible();
  await waitFor(() => expect(summary).toHaveBeenCalledTimes(1));

  await userEvent.click(screen.getByRole("button", { name: /查看分析任务/ }));
  expect(onNavigate).toHaveBeenCalledWith("analysis-tasks");
});

test("再次进入首页立即显示缓存并在后台更新", async () => {
  let resolveRefresh;
  summary
    .mockResolvedValueOnce({
      actions: [
        {
          type: "blocked",
          object_type: "task",
          object_id: "task-cached",
          title: "缓存中的待办",
          target: { route: "tasks", task_id: "task-cached" },
        },
      ],
      recent_outputs: [],
      counts: {},
    })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRefresh = resolve;
        }),
    );
  const view = render(<WorkbenchPage onNavigate={vi.fn()} />);
  expect(await screen.findByText("缓存中的待办")).toBeVisible();

  view.rerender(<div>其他模块</div>);
  view.rerender(<WorkbenchPage onNavigate={vi.fn()} />);

  expect(screen.getByText("缓存中的待办")).toBeVisible();
  expect(screen.queryByText("正在读取待行动事项…")).not.toBeInTheDocument();
  await waitFor(() => expect(summary).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(document.querySelectorAll(".inline-loading.ant-spin-spinning")).toHaveLength(
      1,
    ),
  );
  expect(screen.getByText("缓存中的待办")).toBeVisible();

  await act(async () => {
    resolveRefresh({
      actions: [],
      recent_outputs: [],
      counts: {},
    });
  });
  expect(await screen.findByText("当前没有待处理事项或后台任务")).toBeVisible();
});

test("首页可直接进入 AI 报告进度和已发布结果", async () => {
  summary.mockResolvedValue({
    actions: [
      {
        type: "report_running",
        status: "running",
        object_type: "ai_insight_report_job",
        object_id: "job-1",
        title: "AI 洞察 · SK002",
        reason: "模型正在解释证据",
        actor: { name: "系统管理员" },
        updated_at: "2026-08-15T09:00:00Z",
        target: {
          route: "analysis-dashboards",
          dashboard_id: "dashboard-1",
          version_id: "dashboard-version-1",
          report_id: "job-1",
          tab: "report",
        },
      },
    ],
    recent_outputs: [
      {
        type: "insight_report",
        version_id: "report-version-1",
        version_no: 1,
        title: "AI 洞察 · SK001",
        updated_at: "2026-08-15T08:00:00Z",
        target: {
          route: "analysis-dashboards",
          dashboard_id: "dashboard-2",
          version_id: "dashboard-version-2",
          report_id: "job-2",
          tab: "report",
        },
      },
    ],
    counts: { running_reports: 1 },
  });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  await userEvent.click(await screen.findByText("AI 洞察 · SK002"));
  expect(window.location.hash).toBe(
    "#analysis-dashboards?dashboard=dashboard-1&version=dashboard-version-1&report=job-1&tab=report",
  );

  await userEvent.click(screen.getByText("AI 洞察 · SK001"));
  expect(window.location.hash).toBe(
    "#analysis-dashboards?dashboard=dashboard-2&version=dashboard-version-2&report=job-2&tab=report",
  );
});

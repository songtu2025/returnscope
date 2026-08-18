import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { summary } = vi.hoisted(() => ({ summary: vi.fn() }));

vi.mock("../src/shared/api/workbenchApi", () => ({ workbenchApi: { summary } }));

import { WorkbenchPage } from "../src/features/workbench/WorkbenchPage";

beforeEach(() => {
  summary.mockReset();
  window.location.hash = "";
});

afterEach(() => cleanup());

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
  expect(summary).toHaveBeenCalledWith(
    5,
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
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

test("需复核待办直接进入创建批次界面", async () => {
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
          action: "review",
        },
      },
    ],
    recent_outputs: [],
    counts: { review_required: 1 },
  });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  await userEvent.click(await screen.findByText("SR002 分类结果"));

  expect(window.location.hash).toContain("result_version_id=result-review-1");
  expect(window.location.hash).toContain("action=review");
  expect(window.location.hash).toContain("tab=history");
});

test("原子汇总失败只显示一个共享错误和一次重试", async () => {
  summary
    .mockRejectedValueOnce(new Error("工作台接口不可用"))
    .mockResolvedValueOnce({ actions: [], recent_outputs: [], counts: {} });

  render(<WorkbenchPage onNavigate={vi.fn()} />);

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText("首页数据读取失败")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "重新加载" })).toHaveLength(1);

  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
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

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { Sidebar, Topbar } from "../src/App";
import { buildHash, parseHash } from "../src/app/hashRouter";
import {
  PRIMARY_NAV_ITEMS,
  SETTINGS_NAV_ITEM,
  routeForDestination,
  routeForTarget,
} from "../src/app/navigation";
import {
  clearTaskDraft,
  readTaskDraft,
  writeTaskDraft,
} from "../src/features/task-create/taskDraftStorage";

describe("应用壳层与路由", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.location.hash = "";
  });

  afterEach(() => cleanup());

  test("一级导航只保留五个稳定业务入口并单列系统设置", () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "首页",
      "产品信息",
      "分析任务",
      "分类结果",
      "分析看板",
    ]);
    expect(SETTINGS_NAV_ITEM.label).toBe("系统设置");
  });

  test("创建任务归属于分析任务且只设置一个当前页面", () => {
    render(<Sidebar page="task-create" system={{}} onNavigate={vi.fn()} />);

    const tasks = screen.getByRole("button", { name: "分析任务" });
    expect(screen.queryByRole("button", { name: "创建任务" })).not.toBeInTheDocument();
    expect(tasks).toHaveClass("active");
    expect(tasks).toHaveAttribute("aria-current", "page");
    expect(
      screen.getAllByRole("button").filter((item) => item.ariaCurrent),
    ).toHaveLength(1);
  });

  test("容量入口先刷新并进入无历史焦点的进行中任务列表", async () => {
    const calls = [];
    const onRefresh = vi.fn(async () => calls.push("refresh"));
    const onNavigate = vi.fn((...args) => calls.push(["navigate", ...args]));
    render(
      <Topbar
        user={{ display_name: "管理员", email: "admin@example.com" }}
        system={{ my_running_segments: 0 }}
        onRefresh={onRefresh}
        onNavigate={onNavigate}
        onSearch={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /我的运行 Listing/ }));
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith("analysis-tasks"));
    expect(calls).toEqual(["refresh", ["navigate", "analysis-tasks"]]);
  });

  test("普通一级导航继续只高亮其业务入口", () => {
    render(<Sidebar page="classification-results" system={{}} onNavigate={vi.fn()} />);

    expect(screen.getByRole("button", { name: "分类结果" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "分类结果" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: "分析任务" })).not.toHaveClass("active");
  });

  test("旧地址被解析为新的业务归属", () => {
    expect(parseHash("#new")).toMatchObject({ page: "task-create", isLegacy: true });
    expect(parseHash("#tasks")).toMatchObject({
      page: "analysis-tasks",
      isLegacy: true,
    });
    expect(parseHash("#results")).toMatchObject({
      page: "legacy-results",
      isLegacy: true,
    });
    expect(parseHash("#api")).toMatchObject({
      page: "settings",
      query: { tab: "api" },
    });
    expect(parseHash("#team")).toMatchObject({
      page: "settings",
      query: { tab: "users" },
    });
    expect(parseHash("#review")).toMatchObject({
      page: "review",
      isLegacy: false,
    });
    expect(
      parseHash("#review-center?review_batch_id=batch-1&result_version_id=v1"),
    ).toMatchObject({
      page: "classification-results",
      query: {
        view: "reviews",
        review_batch_id: "batch-1",
        result_version_id: "v1",
      },
      isLegacy: true,
    });
  });

  test("实体选择和筛选由 URL 承载", () => {
    expect(
      routeForDestination("analysis-tasks", { kind: "task", id: "task-1" }),
    ).toEqual({ page: "analysis-tasks", query: { task_id: "task-1" } });
    expect(
      routeForDestination("classification-results", {
        kind: "classification-result",
        id: "result-1",
      }),
    ).toEqual({
      page: "classification-results",
      query: { result_version_id: "result-1" },
    });
    expect(
      routeForDestination("review-center", {
        kind: "review-batch",
        id: "batch-1",
      }),
    ).toEqual({
      page: "classification-results",
      query: { view: "reviews", review_batch_id: "batch-1" },
    });
    expect(buildHash("data-assets", { view: "quality", page: 2, empty: "" })).toBe(
      "#data-assets?view=quality&page=2",
    );
    expect(buildHash("settings", { tab: "audit", page: 3 })).toBe(
      "#settings?tab=audit&page=3",
    );
  });

  test("审计目标映射到各领域页的精确实体", () => {
    expect(
      routeForTarget({ route: "tasks", task_id: "task-1", segment_id: "seg-2" }),
    ).toEqual({
      page: "analysis-tasks",
      query: { task_id: "task-1", segment_id: "seg-2" },
    });
    expect(
      routeForTarget({
        route: "review",
        review_id: "review-1",
        workflow_status: "pending",
      }),
    ).toEqual({
      page: "review",
      query: { review: "review-1", status: "pending" },
    });
    expect(routeForTarget({ route: "review-center", batch_id: "batch-1" })).toEqual({
      page: "classification-results",
      query: { view: "reviews", review_batch_id: "batch-1" },
    });
    expect(
      routeForTarget({
        route: "data",
        dataset_id: "dataset-1",
        view: "products",
      }),
    ).toEqual({
      page: "data-assets",
      query: { dataset: "dataset-1", view: "products" },
    });
    expect(
      routeForTarget({
        route: "api",
        tab: "models",
        connection_id: "connection-1",
        config_version_id: "config-2",
        model_id: "model-3",
      }),
    ).toEqual({
      page: "settings",
      query: {
        tab: "models",
        connection_id: "connection-1",
        config_version_id: "config-2",
        model_id: "model-3",
      },
    });
    expect(routeForTarget({ route: "team", tab: "users", user_id: "user-2" })).toEqual({
      page: "settings",
      query: { tab: "users", user_id: "user-2" },
    });
    expect(routeForTarget(null)).toBeNull();
  });

  test("未提交任务草稿在会话内恢复", () => {
    writeTaskDraft("user-1", {
      step: 2,
      form: { dataset_version_id: "returns-v2" },
      resumePreflight: true,
    });
    expect(readTaskDraft("user-1")).toEqual({
      step: 2,
      form: { dataset_version_id: "returns-v2" },
      resumePreflight: true,
    });
  });

  test("任务草稿按用户隔离且只清理当前用户", () => {
    writeTaskDraft("user-1", { step: 1, taskName: "用户一任务" });
    writeTaskDraft("user-2", { step: 2, taskName: "用户二任务" });

    expect(readTaskDraft("user-1")).toEqual({ step: 1, taskName: "用户一任务" });
    expect(readTaskDraft("user-2")).toEqual({ step: 2, taskName: "用户二任务" });

    clearTaskDraft("user-1");
    expect(readTaskDraft("user-1")).toBeNull();
    expect(readTaskDraft("user-2")).toEqual({ step: 2, taskName: "用户二任务" });
  });
});

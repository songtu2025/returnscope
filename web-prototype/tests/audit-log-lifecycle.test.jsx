import { cleanup, screen } from "@testing-library/react";
import { renderWithServerState as render } from "./renderWithServerState";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

const { logs } = vi.hoisted(() => ({ logs: vi.fn() }));
vi.mock("../src/shared/api/auditApi", () => ({ auditApi: { logs } }));
import { AuditLogPage } from "../src/features/system-settings/AuditLogPage";
afterEach(cleanup);

test.each([
  ["segment_delete", "移除 Listing"],
  ["segment_restore", "恢复 Listing"],
  ["segment_remove_requested", "请求移除 Listing"],
  ["remove", "移入回收站"],
  ["remove_failed", "移除失败"],
  ["purge", "永久删除"],
  ["restore", "恢复"],
])("生命周期审计 %s 显示中文并保留对象定位和筛选代码", async (action, label) => {
  const entity_type = action.startsWith("segment_") ? "task" : "task_segment";
  const target = { route: "tasks", task_id: "task-1" };
  if (entity_type === "task_segment") target.segment_id = "segment-1";
  const item = { id: "audit-1", action, entity_type, target };
  logs.mockResolvedValue({ total: 1, items: [item] });
  render(<AuditLogPage route={{ query: { action } }} />);
  expect(await screen.findByText(label, { selector: "td" })).toBeVisible();
  expect(screen.getByLabelText("操作")).toHaveValue(action);
  expect(screen.getByRole("option", { name: label })).toHaveValue(action);
  const objectLabel = entity_type === "task" ? "分析任务" : "Listing 片段";
  expect(screen.getByText(objectLabel, { selector: "b" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /查看对象/ }));
  expect(window.location.hash).toContain("#analysis-tasks?task_id=task-1");
  expect(window.location.hash.includes("segment_id=")).toBe(
    entity_type === "task_segment",
  );
  await userEvent.click(screen.getByRole("button", { name: "筛选" }));
  expect(window.location.hash).toContain(`action=${action}`);
});

test.each(["task", "ai_insight_report"])(
  "%s 的取消操作使用通用中文含义",
  async (entity_type) => {
    logs.mockResolvedValue({
      total: 1,
      items: [{ id: "cancel", entity_type, action: "cancel" }],
    });
    render(<AuditLogPage route={{ query: {} }} />);
    expect(await screen.findByText("取消", { selector: "td" })).toBeVisible();
    expect(screen.getByRole("option", { name: "取消" })).toHaveValue("cancel");
  },
);

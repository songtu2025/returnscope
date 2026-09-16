import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { logs } = vi.hoisted(() => ({ logs: vi.fn() }));

vi.mock("../src/shared/api/auditApi", () => ({ auditApi: { logs } }));

import { AuditLogPage } from "../src/features/system-settings/AuditLogPage";

beforeEach(() => {
  logs.mockReset();
  window.location.hash = "";
});

afterEach(() => cleanup());

test("审计记录按字段对齐展示差异、掩码敏感值并精确跳转", async () => {
  logs.mockResolvedValue({
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        id: "audit-1",
        actor_name: "系统管理员",
        action: "legacy_result_backfill_prepare",
        entity_type: "review_batch",
        entity_id: "batch-1",
        created_at: "2026-08-12T10:00:00Z",
        before: {
          status: "draft",
          actor: "user-1",
          preview_hash: "preview-old",
          result_publish_status: "publishing",
          segment_id: "segment-1",
          future_field: "old-value",
          api_key: "old-secret",
        },
        after: {
          status: "resolved",
          actor: "user-2",
          preview_hash: "preview-new",
          result_publish_status: "published",
          segment_id: "segment-1",
          future_field: "new-value",
          api_key: "new-secret",
        },
        target: { route: "review-center", batch_id: "batch-1" },
      },
    ],
  });

  render(
    <AuditLogPage route={{ query: { entity_type: "review_batch", page: "1" } }} />,
  );

  expect(await screen.findByText("系统管理员")).toBeVisible();
  expect(screen.getByText("准备回填历史结果")).toBeVisible();
  expect(
    screen.getByText("legacy_result_backfill_prepare", { selector: "code" }),
  ).toBeVisible();
  expect(screen.getByText("复核批次")).toBeVisible();
  expect(screen.getByText("review_batch", { selector: "code" })).toBeVisible();
  await userEvent.click(screen.getByText("查看字段差异"));
  const apiKeyRow = screen.getByText("api_key").closest("div");
  expect(within(apiKeyRow).getAllByText("••••••")).toHaveLength(2);
  expect(screen.queryByText("old-secret")).not.toBeInTheDocument();
  expect(screen.getByText("draft")).toBeVisible();
  expect(screen.getByText("resolved")).toBeVisible();
  expect(screen.getByText("预检哈希")).toBeVisible();
  expect(screen.getByText("preview_hash", { selector: "code" })).toBeVisible();
  expect(screen.getByText("操作人")).toBeVisible();
  expect(screen.getByText("actor", { selector: "code" })).toBeVisible();
  expect(screen.getByText("结果发布状态")).toBeVisible();
  expect(screen.getByText("result_publish_status", { selector: "code" })).toBeVisible();
  expect(screen.getByText("Listing 片段 ID")).toBeVisible();
  expect(screen.getByText("segment_id", { selector: "code" })).toBeVisible();
  expect(screen.getByText("future_field")).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: /查看对象/ }));
  expect(window.location.hash).toBe(
    "#classification-results?view=reviews&review_batch_id=batch-1",
  );
  expect(logs).toHaveBeenCalledWith(
    expect.objectContaining({
      entity_type: "review_batch",
      page: 1,
      page_size: 20,
    }),
    expect.objectContaining({ signal: expect.anything() }),
  );
});

test("审计日期参数由 URL 恢复且错误范围不发请求", async () => {
  render(
    <AuditLogPage
      route={{
        query: {
          date_from: "2026-08-12",
          date_to: "2026-08-01",
          page: "1",
        },
      }}
    />,
  );

  expect(await screen.findByText("日期范围有误")).toBeVisible();
  expect(screen.getByText("结束日期不能早于开始日期。")).toBeVisible();
  expect(screen.getByLabelText("开始日期")).toHaveValue("2026-08-12");
  expect(screen.getByLabelText("结束日期")).toHaveValue("2026-08-01");
  expect(logs).not.toHaveBeenCalled();
});

test("审计筛选拒绝错误日期并隐藏旧结果", async () => {
  const user = userEvent.setup();
  const originalHash = "#settings?tab=audit&entity_type=task";
  window.location.hash = originalHash;
  logs.mockResolvedValue({
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        id: "audit-old",
        actor_name: "原有记录",
        action: "task_create",
        entity_type: "task",
        entity_id: "task-1",
        created_at: "2026-08-01T10:00:00Z",
        before: null,
        after: null,
      },
    ],
  });

  render(<AuditLogPage route={{ query: { entity_type: "task" } }} />);

  expect(await screen.findByText("原有记录")).toBeVisible();
  const dateFrom = screen.getByLabelText("开始日期");
  const dateTo = screen.getByLabelText("结束日期");
  await user.type(dateFrom, "2026-08-12");
  await user.type(dateTo, "2026-08-01");

  expect(screen.getByText("结束日期不能早于开始日期。")).toBeVisible();
  expect(screen.queryByText("原有记录")).not.toBeInTheDocument();
  expect(dateTo).toHaveAttribute("aria-invalid", "true");
  expect(dateTo).toHaveAttribute("aria-describedby", "audit-date-to-error");

  await user.click(screen.getByRole("button", { name: "筛选" }));

  expect(document.activeElement).toBe(dateTo);
  expect(window.location.hash).toBe(originalHash);
  expect(logs).toHaveBeenCalledTimes(1);
});

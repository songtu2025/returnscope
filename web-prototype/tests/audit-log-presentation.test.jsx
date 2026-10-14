import { cleanup, screen, within } from "@testing-library/react";
import { renderWithServerState as render } from "./renderWithServerState";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";
import { AuditLogEntries } from "../src/features/system-settings/AuditLogEntries";
import { AuditDiff } from "../src/features/system-settings/AuditLogDiff";

afterEach(() => cleanup());

test.each([
  [{ target: { view: "products" }, after: { kind: "returns" } }, "产品信息"],
  [{ after: { kind: "products" } }, "产品信息"],
  [{ after: { kind: "returns" } }, "用户反馈数据"],
  [{ after: { version: 1 }, before: { kind: "returns" } }, "用户反馈数据"],
  [{ before: null, after: null }, "数据集"],
  [{ after: { kind: "unknown" } }, "数据集"],
  [{ before: "历史描述", after: 1 }, "数据集"],
])("审计按已有对象信息显示名称，未知类型不误标：%s", (context, label) => {
  render(
    <AuditLogEntries
      items={[{ id: "audit-dataset", entity_type: "dataset", ...context }]}
    />,
  );
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.queryByText("dataset", { selector: "code" })).toBeNull();
  expect(screen.queryByText("数据资产")).not.toBeInTheDocument();
});

test("产品信息审计支持键盘打开原有对象链接，其他对象名称不受影响", async () => {
  const user = userEvent.setup();
  render(
    <AuditLogEntries
      items={[
        {
          id: "audit-product",
          entity_type: "dataset",
          entity_id: "products-1",
          target: { route: "data", view: "products", dataset_id: "products-1" },
        },
        { id: "audit-task", entity_type: "task", after: { kind: "products" } },
      ]}
    />,
  );
  expect(screen.getByText("产品信息")).toBeVisible();
  expect(screen.getByText("分析任务")).toBeVisible();
  await user.tab();
  expect(screen.getByRole("button", { name: "查看对象" })).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(window.location.hash).toBe("#data-assets?dataset=products-1&view=products");
});

test.each([
  ["manual_correction", "人工修正语义"],
  ["product_update", "更新产品信息"],
  ["dimension_row_update", "修改产品信息"],
])("新业务审计动作使用中文名称：%s", (action, label) => {
  render(
    <AuditLogEntries
      items={[{ id: "synthetic-action", action, entity_type: "classification_result" }]}
    />,
  );
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.queryByText(action, { selector: "code" })).toBeNull();
});

test("详情仅默认展示变化，数组比较保留结构且敏感值不会泄露", async () => {
  render(
    <AuditDiff
      before={{
        name: "旧名称",
        status: "ready",
        values: ["a,b"],
        records: [{ api_key: "旧密钥" }],
      }}
      after={{
        name: "新名称",
        status: "ready",
        values: ["a", "b"],
        records: [{ api_key: "新密钥" }],
      }}
    />,
  );
  expect(screen.getByText("字段变化 · 3 项")).toBeVisible();
  expect(screen.getByText("旧名称")).toBeVisible();
  expect(screen.getByText('["a,b"]')).toBeVisible();
  expect(screen.getByText('["a","b"]')).toBeVisible();
  expect(screen.getAllByText("ready")[0]).not.toBeVisible();
  expect(document.body.textContent).not.toContain("旧密钥");
  expect(document.body.textContent).not.toContain("新密钥");
  await userEvent.click(screen.getByText("未变化字段 · 1 项"));
  expect(screen.getAllByText("ready")[0]).toBeVisible();
});

test("模型名称优先，原始标识可在详情核对，未知动作保持原值", async () => {
  render(
    <AuditLogEntries
      items={[
        {
          id: "synthetic-model",
          action: "validate",
          entity_type: "api_model",
          entity_id: "model-synthetic",
          after: { display_name: "合成模型" },
        },
        {
          id: "synthetic-unknown",
          action: "future_action",
          entity_type: "future_entity",
        },
      ]}
    />,
  );
  expect(screen.getByText("合成模型")).toBeVisible();
  expect(screen.getByText("验证")).toBeVisible();
  expect(screen.getByText("future_action")).toBeVisible();
  expect(screen.queryByText("model-synthetic")).toBeNull();
  await userEvent.click(
    within(screen.getByText("合成模型").closest("tr")).getByRole("button", {
      name: "查看详情",
    }),
  );
  expect(screen.getByText("model-synthetic")).toBeVisible();
  expect(screen.getByText("api_model", { selector: "code" })).toBeVisible();
});

test("系统审计按产品增量记录显示实际变更，历史原值不被修改", async () => {
  const before = {
    row_index: 0,
    values: { MSKU: "合成SKU", Listing: "L1", 产品名称: "旧名称" },
  };
  const after = { row_index: 0, values: { 产品名称: "新名称" } };
  render(
    <AuditLogEntries
      items={[
        {
          id: "partial",
          entity_type: "dataset",
          action: "dimension_row_update",
          before,
          after,
        },
      ]}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "查看详情" }));
  expect(screen.getByText("字段变化 · 1 项")).toBeVisible();
  expect(screen.getByText("旧名称")).toBeVisible();
  expect(screen.getByText("新名称")).toBeVisible();
  expect(screen.getAllByText("合成SKU")[0]).not.toBeVisible();
  expect(after.values).toEqual({ 产品名称: "新名称" });
  expect(before.values.MSKU).toBe("合成SKU");
});

test.each(["", null])("增量记录保留显式清空字段：%s", (empty) => {
  render(
    <AuditDiff
      partialAfter
      before={{ name: "旧名称", count: 0 }}
      after={{ name: empty }}
    />,
  );
  expect(screen.getByText("字段变化 · 1 项")).toBeVisible();
  const table = screen.getAllByRole("table", { name: "字段差异" })[0];
  expect(within(table).getByText("未提供")).toBeVisible();
  expect(within(table).queryByText("0")).toBeNull();
});

test("完整快照缺失字段仍按删除展示，不套用增量规则", () => {
  render(<AuditDiff before={{ name: "旧名称", count: 0 }} after={{ count: 0 }} />);
  expect(screen.getByText("字段变化 · 1 项")).toBeVisible();
  expect(screen.getByText("旧名称")).toBeVisible();
  expect(screen.getByText("未提供")).toBeVisible();
});

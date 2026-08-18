import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { importRules, dataVersionReferences } = vi.hoisted(() => ({
  importRules: vi.fn(),
  dataVersionReferences: vi.fn(),
}));

vi.mock("../src/shared/api/dataApi", () => ({ dataApi: { importRules } }));
vi.mock("../src/api", () => ({
  api: { dataVersionReferences },
}));

import { ImportRulesPage } from "../src/features/data-management/ImportRulesPage";
import { DatasetReferences } from "../src/pages/DataManagement";

beforeEach(() => {
  importRules.mockReset();
  dataVersionReferences.mockReset();
  window.location.hash = "";
});

afterEach(() => cleanup());

test("导入规则页只读展示真实系统规则与折叠技术信息", async () => {
  importRules.mockResolvedValue({
    items: [
      {
        id: "returns-standard-v1",
        kind: "returns",
        name: "退货标准导入规则",
        version: 1,
        status: "active",
        source: "system",
        file_extensions: [".xlsx", ".csv"],
        worksheet: "returns",
        required_columns: ["store_site", "sku", "order-id"],
        optional_columns: ["comment"],
        match_key: ["store_site", "sku"],
        notes: ["退货SKU通过商品目录 MSKU 匹配"],
        content_hash: "hash-1",
      },
    ],
  });

  render(<ImportRulesPage />);

  expect(await screen.findByText("退货标准导入规则")).toBeVisible();
  expect(screen.getByText("store_site、sku、order-id")).toBeVisible();
  expect(screen.getByText("store_site、sku")).toBeVisible();
  expect(screen.getByText("技术信息")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /编辑|发布|修改/ }),
  ).not.toBeInTheDocument();
  expect(importRules).toHaveBeenCalledTimes(1);
});

test("导入规则失败只提供真实重试", async () => {
  importRules
    .mockRejectedValueOnce(new Error("规则接口不可用"))
    .mockResolvedValueOnce({ items: [] });
  render(<ImportRulesPage />);

  expect(await screen.findByText("导入规则读取失败")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(await screen.findByText("暂无生效的导入规则")).toBeVisible();
  expect(importRules).toHaveBeenCalledTimes(2);
});

test("数据版本引用显示历史任务固化快照并精确跳转", async () => {
  dataVersionReferences.mockResolvedValue({
    version: { id: "returns-v2", name: "SEEKWAY 退货数据", version: 2 },
    total: 1,
    page: 1,
    page_size: 20,
    items: [
      {
        reference_type: "returns",
        task_id: "task-1",
        title: "八月退货分析",
        status: "paused",
        owner: { id: "user-1", name: "系统管理员" },
        created_at: "2026-08-12T10:00:00Z",
        version_snapshot: { dataset_version_id: "returns-v2", version: 2 },
      },
    ],
  });
  const onNavigate = vi.fn();

  render(
    <DatasetReferences
      versions={[{ id: "returns-v2", version: 2, original_name: "returns.xlsx" }]}
      currentVersionId="returns-v2"
      routeVersionId="returns-v2"
      page={1}
      onRouteChange={vi.fn()}
      onNavigate={onNavigate}
    />,
  );

  expect(await screen.findByText("八月退货分析")).toBeVisible();
  expect(screen.getByText(/已暂停 · 系统管理员/)).toBeVisible();
  expect(screen.queryByText(/paused ·/)).not.toBeInTheDocument();
  expect(screen.getByText("固化版本快照")).toBeVisible();
  await userEvent.click(screen.getByText("固化版本快照"));
  expect(
    within(screen.getByText("dataset_version_id").closest("div")).getByText(
      "returns-v2",
    ),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /查看任务/ }));
  expect(onNavigate).toHaveBeenCalledWith("analysis-tasks", {
    kind: "task",
    id: "task-1",
  });
  expect(dataVersionReferences).toHaveBeenCalledWith(
    "returns-v2",
    { page: 1, page_size: 20 },
    expect.objectContaining({ signal: expect.anything() }),
  );
});

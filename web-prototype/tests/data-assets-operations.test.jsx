import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { importRules, inspectReturnImport, importReturns, dataVersionReferences } =
  vi.hoisted(() => ({
    importRules: vi.fn(),
    inspectReturnImport: vi.fn(),
    importReturns: vi.fn(),
    dataVersionReferences: vi.fn(),
  }));

vi.mock("../src/shared/api/dataApi", () => ({
  dataApi: {
    importRules,
  },
}));
vi.mock("../src/api", () => ({
  api: { dataVersionReferences, inspectReturnImport, importReturns },
}));

import { ImportRulesPage } from "../src/features/data-management/ImportRulesPage";
import { ReturnImportDialog } from "../src/features/task-create/ReturnImportDialog";
import { DatasetReferences } from "../src/features/data-management/DatasetReferences";
import { renderWithServerState as render } from "./renderWithServerState";

beforeEach(() => {
  importRules.mockReset();
  inspectReturnImport.mockReset();
  importReturns.mockReset();
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

test("退货文件检查失败后可重新选择 XLSX 修正文件", async () => {
  const user = userEvent.setup();
  const correctedFile = new File(["xlsx"], "returns.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  inspectReturnImport
    .mockRejectedValueOnce(new Error("Failed to fetch"))
    .mockResolvedValueOnce({
      inspection_id: "inspection-2",
      original_name: "returns.xlsx",
      suggested_name: "修正后的退货数据",
      row_count: 1,
      stores: ["BRAND:US"],
      quality: { valid_comment_rows: 1, missing_store_rows: 0 },
      matches: [],
    });

  render(<ReturnImportDialog onClose={vi.fn()} onDone={vi.fn()} />);

  const fileInput = document.querySelector('input[type="file"]');
  await user.upload(fileInput, new File(["broken"], "returns.csv"));
  expect(fileInput).toHaveValue("");
  await user.click(screen.getByRole("button", { name: "检查文件" }));
  expect(
    await screen.findByText(
      "无法连接服务，请确认 CSV 或 XLSX 格式正确，修正后重新选择文件并检查。",
    ),
  ).toBeVisible();
  expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();

  await user.upload(fileInput, correctedFile);
  expect(
    screen.queryByText(/请确认 CSV 或 XLSX 格式正确，修正后重新选择文件并检查。/),
  ).not.toBeInTheDocument();
  expect(inspectReturnImport).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "检查文件" }));
  expect(await screen.findByText("文件检查完成")).toBeVisible();
  expect(inspectReturnImport).toHaveBeenCalledTimes(2);
  expect(inspectReturnImport.mock.calls[1][0].get("file")).toBe(correctedFile);

  await user.click(screen.getByRole("button", { name: "更换文件" }));
  expect(screen.getByText("选择 CSV 或 XLSX 文件")).toBeVisible();
  expect(screen.getByRole("button", { name: "检查文件" })).toBeDisabled();
});

async function inspectSyntheticImport(_purpose, overrides = {}, onDone = vi.fn()) {
  const user = userEvent.setup();
  inspectReturnImport.mockResolvedValue({
    inspection_id: "synthetic-inspection",
    original_name: "SYNTHETIC.csv",
    suggested_name: "  合成数据源  ",
    row_count: 2,
    stores: ["SYNTHETIC:US"],
    quality: { valid_comment_rows: 2, missing_store_rows: 0 },
    matches: [],
    ...overrides,
  });
  render(<ReturnImportDialog onClose={vi.fn()} onDone={onDone} />);
  await user.upload(
    document.querySelector('input[type="file"]'),
    new File(["synthetic"], "SYNTHETIC.csv"),
  );
  await user.click(screen.getByRole("button", { name: "检查文件" }));
  await screen.findByText("文件检查完成");
  return user;
}

test("任务上传仅支持分析本批，提交不携带长期数据源字段", async () => {
  const onDone = vi.fn();
  const result = { version_id: "synthetic-version", mode: "analyze_only" };
  importReturns.mockResolvedValue(result);
  const user = await inspectSyntheticImport("task", {}, onDone);
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "导入并分析本批" }));
  await waitFor(() => expect(onDone).toHaveBeenCalledWith(result));
  expect(importReturns).toHaveBeenCalledExactlyOnceWith({
    inspection_id: "synthetic-inspection",
    mode: "analyze_only",
  });
});

test("重复批次允许直接复用，店铺缺失仍阻断提交", async () => {
  const duplicate = { dataset_name: "合成已有源" };
  const user = await inspectSyntheticImport("task", { duplicate });
  expect(screen.getByRole("button", { name: "使用已导入的数据" })).toBeEnabled();
  cleanup();
  await inspectSyntheticImport("task", {
    duplicate,
    quality: { valid_comment_rows: 2, missing_store_rows: 1 },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("行缺少店铺/站点");
  const button = screen.getByRole("button", { name: "请先修正文件" });
  expect(button).toBeDisabled();
  await user.click(button);
  expect(importReturns).not.toHaveBeenCalled();
});

test("任务上传支持 CSV 和 XLSX", () => {
  const { unmount } = render(<ReturnImportDialog onClose={vi.fn()} onDone={vi.fn()} />);
  expect(document.querySelector('input[type="file"]')).toHaveAttribute(
    "accept",
    ".csv,.xlsx",
  );
  unmount();
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

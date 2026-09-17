import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const {
  importRules,
  managedDatasets,
  dataset,
  datasetStorageSummary,
  cleanupDatasetStorage,
  datasetRows,
  datasetDownloadUrl,
  inspectReturnImport,
  importReturns,
  dataVersionReferences,
} = vi.hoisted(() => ({
  importRules: vi.fn(),
  managedDatasets: vi.fn(),
  dataset: vi.fn(),
  datasetStorageSummary: vi.fn(),
  cleanupDatasetStorage: vi.fn(),
  datasetRows: vi.fn(),
  datasetDownloadUrl: vi.fn(),
  inspectReturnImport: vi.fn(),
  importReturns: vi.fn(),
  dataVersionReferences: vi.fn(),
}));

vi.mock("../src/shared/api/dataApi", () => ({
  dataApi: {
    importRules,
    managedDatasets,
    dataset,
    datasetStorageSummary,
    cleanupDatasetStorage,
    datasetRows,
    datasetDownloadUrl,
  },
}));
vi.mock("../src/api", () => ({
  api: { dataVersionReferences, inspectReturnImport, importReturns },
}));

import { ImportRulesPage } from "../src/features/data-management/ImportRulesPage";
import { ReturnDataAssetsPage } from "../src/features/data-management/ReturnDataAssetsPage";
import { ReturnImportDialog } from "../src/features/task-create/ReturnImportDialog";
import { DatasetUploadDialog } from "../src/components/DatasetUploadDialog";
import { DatasetReferences } from "../src/pages/DataManagement";

beforeEach(() => {
  importRules.mockReset();
  managedDatasets.mockReset();
  dataset.mockReset();
  datasetStorageSummary.mockReset();
  cleanupDatasetStorage.mockReset();
  datasetRows.mockReset();
  datasetDownloadUrl.mockReset();
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

test("退货数据源页集中展示当前状态并从详情按需查看历史", async () => {
  const user = userEvent.setup();
  const summary = {
    id: "returns-1",
    source_key: "senwayzon-ca-us",
    name: "SENWAYZON CA、SENWAYZON US 退货数据",
    source_name: "SENWAYZON CA、SENWAYZON US 退货数据",
    version_id: "returns-v6",
    row_count: 26439,
    task_reference_count: 3,
    updated_at: "2026-08-25T04:32:00Z",
    quality: {
      stores: ["SENWAYZON:CA", "SENWAYZON:US"],
      valid_comment_rows: 19789,
      matching_key_ready_rate: 100,
    },
  };
  managedDatasets.mockResolvedValue([summary]);
  dataset.mockResolvedValue({
    ...summary,
    creator_name: "数据管理员",
    imports: [
      {
        id: "import-1",
        resulting_version_id: "returns-v6",
        mode: "append",
        original_name: "returns-0825.csv",
        row_count: 2184,
        imported_row_count: 1067,
        skipped_row_count: 1117,
        creator_name: "数据管理员",
        created_at: "2026-08-25T04:32:00Z",
      },
    ],
    versions: [
      {
        id: "returns-v6",
        dataset_id: "returns-1",
        version: 6,
        original_name: "returns-0825.csv",
        row_count: 26439,
        creator_name: "数据管理员",
        change_note: "日常增量导入",
        created_at: "2026-08-25T04:32:00Z",
      },
      {
        id: "returns-v5",
        dataset_id: "returns-1",
        version: 5,
        original_name: "returns-0824.csv",
        row_count: 25372,
        creator_name: "数据管理员",
        change_note: "首次导入",
        created_at: "2026-08-24T04:32:00Z",
      },
      {
        id: "returns-v4",
        dataset_id: "returns-1",
        version: 4,
        original_name: "returns-0823.csv",
        row_count: 24980,
        created_at: "2026-08-23T04:32:00Z",
      },
      {
        id: "returns-v3",
        dataset_id: "returns-1",
        version: 3,
        original_name: "returns-0822.csv",
        row_count: 24110,
        created_at: "2026-08-22T04:32:00Z",
      },
      {
        id: "returns-v2",
        dataset_id: "returns-1",
        version: 2,
        original_name: "returns-0821.csv",
        row_count: 23720,
        created_at: "2026-08-21T04:32:00Z",
      },
      {
        id: "returns-v1",
        dataset_id: "returns-1",
        version: 1,
        original_name: "returns-0820.csv",
        row_count: 22950,
        created_at: "2026-08-20T04:32:00Z",
      },
    ],
  });
  datasetStorageSummary.mockResolvedValue({
    version_count: 6,
    logical_bytes: 503867830,
    physical_bytes: 251933915,
    current_versions: 1,
    task_referenced_versions: 3,
    task_reference_count: 3,
    duplicate_groups: 2,
    dedup_reclaimable_bytes: 82112954,
    expired_versions: 0,
    expired_reclaimable_bytes: 0,
    retention_days: 30,
    retain_latest: 2,
    can_cleanup: true,
  });
  datasetRows.mockResolvedValue({
    records: [
      {
        "order-id": "O-1001",
        sku: "SMRG106-Carmine-L",
        "customer-comments": "尺码偏小",
        _row_index: 0,
      },
    ],
    source_total: 26439,
    version: 6,
  });
  datasetDownloadUrl.mockReturnValue("/api/datasets/returns-1/download?version=6");
  inspectReturnImport.mockResolvedValue({
    inspection_id: "inspection-1",
    original_name: "returns-0826.csv",
    suggested_name: "SENWAYZON 退货数据",
    row_count: 500,
    stores: ["SENWAYZON:CA", "SENWAYZON:US"],
    quality: { valid_comment_rows: 480, missing_store_rows: 0 },
    matches: [
      {
        dataset_id: "returns-1",
        dataset_name: "SENWAYZON 退货数据",
        row_count: 26439,
      },
    ],
  });

  render(
    <ReturnDataAssetsPage
      route={{ query: {} }}
      notify={vi.fn()}
      onRouteChange={vi.fn()}
    />,
  );

  expect(await screen.findByRole("heading", { name: "退货数据源管理" })).toBeVisible();
  expect(screen.getByText("SENWAYZON CA、SENWAYZON US 退货数据")).toBeVisible();
  expect(screen.getByText("SENWAYZON:CA · SENWAYZON:US")).toBeVisible();
  expect(screen.getByText("3 个任务")).toBeVisible();
  expect(await screen.findByText("最近导入摘要")).toBeVisible();
  expect(screen.getByText("日常增量导入")).toBeVisible();
  expect(dataset).toHaveBeenCalledTimes(1);
  expect(dataset).toHaveBeenCalledWith(
    "returns-1",
    expect.objectContaining({ include: "versions,imports" }),
  );
  expect(screen.queryByText("历史快照")).not.toBeInTheDocument();

  const detailButton = screen.getByRole("button", { name: "收起详情" });
  expect(detailButton).toHaveAttribute("aria-expanded", "true");
  await user.click(detailButton);
  expect(screen.queryByText("最近导入摘要")).not.toBeInTheDocument();
  const reopenButton = screen.getByRole("button", { name: "查看详情" });
  expect(reopenButton).toHaveAttribute("aria-expanded", "false");
  await user.click(reopenButton);
  expect(await screen.findByText("最近导入摘要")).toBeVisible();
  expect(screen.getByRole("button", { name: "收起详情" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "查看追溯记录" }));
  expect(screen.getByText(/完整快照/)).toBeVisible();
  expect(screen.getByText("当前快照")).toBeVisible();
  expect(screen.getAllByText("历史快照")).toHaveLength(4);
  expect(await screen.findByText("240 MiB")).toBeVisible();
  expect(screen.getByText("78 MiB")).toBeVisible();
  expect(screen.getByText("第 1 / 2 页")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "下一页快照" }));
  expect(screen.getByText(/returns-0820\.csv/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "上一页快照" }));

  await user.click(screen.getByRole("button", { name: "管理存储" }));
  const storageDialog = screen.getByRole("dialog", { name: "快照存储管理" });
  const cleanupButton = within(storageDialog).getByRole("button", {
    name: "开始安全清理",
  });
  expect(cleanupButton).toBeDisabled();
  await user.click(within(storageDialog).getByRole("checkbox"));
  expect(cleanupButton).toBeEnabled();
  await user.click(within(storageDialog).getByRole("button", { name: "关闭" }));

  await user.click(
    screen.getByRole("button", { name: /查看当前快照内容：returns-0825.csv/ }),
  );
  const snapshotDialog = await screen.findByRole("dialog", {
    name: "当前快照内容",
  });
  expect(within(snapshotDialog).getByText("O-1001")).toBeVisible();
  expect(within(snapshotDialog).getByText("尺码偏小")).toBeVisible();
  expect(within(snapshotDialog).getByText("日常增量导入")).toBeVisible();
  expect(
    within(snapshotDialog).getByRole("link", { name: "下载此快照" }),
  ).toHaveAttribute("href", "/api/datasets/returns-1/download?version=6");
  expect(datasetRows).toHaveBeenCalledWith(
    "returns-1",
    "",
    0,
    10,
    { version: 6 },
    expect.objectContaining({ signal: expect.anything() }),
  );
  await user.click(within(snapshotDialog).getByRole("button", { name: "关闭" }));

  await user.click(screen.getByRole("button", { name: "导入新批次" }));
  const fileInput = document.querySelector('input[type="file"]');
  await user.upload(fileInput, new File(["a,b"], "returns-0826.csv"));
  await user.click(screen.getByRole("button", { name: "检查文件" }));
  expect(await screen.findByText("追加到已有数据源")).toBeVisible();
  expect(screen.queryByText("仅分析本批")).not.toBeInTheDocument();
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

  render(<ReturnImportDialog purpose="asset" onClose={vi.fn()} onDone={vi.fn()} />);

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

test("两个退货上传入口都声明支持 CSV 和 XLSX", () => {
  const { unmount } = render(
    <ReturnImportDialog purpose="asset" onClose={vi.fn()} onDone={vi.fn()} />,
  );
  expect(document.querySelector('input[type="file"]')).toHaveAttribute(
    "accept",
    ".csv,.xlsx",
  );
  unmount();

  render(
    <DatasetUploadDialog
      dialog={{ mode: "create", kind: "returns" }}
      onClose={vi.fn()}
      onDone={vi.fn()}
    />,
  );
  expect(document.querySelector('input[type="file"]')).toHaveAttribute(
    "accept",
    ".csv,.xlsx",
  );
  expect(screen.getByText("选择 CSV 或 XLSX 文件")).toBeVisible();
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

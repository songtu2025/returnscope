import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    dataVersions: vi.fn(),
    configs: vi.fn(),
    status: vi.fn(),
    preflightTask: vi.fn(),
    inspectReturnImport: vi.fn(),
    importReturns: vi.fn(),
    mysqlReturnSchema: vi.fn(),
    previewMysqlReturns: vi.fn(),
    importMysqlReturns: vi.fn(),
  },
}));
vi.mock("../src/api", () => ({ api: apiMock }));

import { NewTaskPage } from "../src/features/task-create/NewTaskPage";
import { renderWithServerState as render } from "./renderWithServerState";

const product = {
  kind: "products",
  version_id: "product-v1",
  dataset_name: "合成产品信息",
  row_count: 1,
};
const importedVersion = {
  id: "import-v1",
  dataset_id: "import-dataset",
  version: 1,
  row_count: 2,
  quality: { valid_comment_rows: 2 },
};
const importedDataset = {
  id: "import-dataset",
  kind: "returns",
  name: "合成用户反馈",
  current_version: 1,
  usage_scope: "task_input",
  versions: [importedVersion],
};
const importResult = {
  version_id: importedVersion.id,
  dataset: importedDataset,
};
const refreshedVersion = {
  ...importedVersion,
  version_id: importedVersion.id,
  dataset_name: importedDataset.name,
  kind: importedDataset.kind,
  current_version: importedDataset.current_version,
  usage_scope: importedDataset.usage_scope,
};

beforeEach(() => {
  vi.resetAllMocks();
  apiMock.dataVersions.mockResolvedValue([product]);
  apiMock.configs.mockResolvedValue([
    {
      id: "synthetic-model-service",
      name: "合成模型服务",
      active_version: { id: "model-v1", primary_model: "synthetic-model" },
    },
  ]);
  apiMock.status.mockResolvedValue({});
  apiMock.preflightTask.mockRejectedValue(new Error("合成预检检查点"));
  apiMock.inspectReturnImport.mockResolvedValue({
    inspection_id: "synthetic-inspection",
    original_name: "SYNTHETIC.csv",
    suggested_name: "合成用户反馈",
    row_count: 2,
    quality: { valid_comment_rows: 2, missing_store_rows: 0 },
  });
  apiMock.importReturns.mockResolvedValue(importResult);
  apiMock.importMysqlReturns.mockResolvedValue(importResult);
  apiMock.mysqlReturnSchema.mockResolvedValue({
    configured: true,
    database: "synthetic",
    table: "synthetic_feedback",
    max_rows: 100,
    fields: [
      { name: "sku", label: "SKU / MSKU", required: true },
      { name: "customer-comments", label: "客户评论", required: true },
      { name: "店铺/站点", label: "店铺/站点" },
    ],
    columns: ["sku", "comment", "store"].map((name) => ({ name, type: "varchar" })),
    mapping: { sku: "sku", "customer-comments": "comment", "店铺/站点": "store" },
  });
  apiMock.previewMysqlReturns.mockResolvedValue({
    row_count: 2,
    over_limit: false,
    missing_store_rows: 0,
    rows: [{ sku: "SYNTHETIC", "customer-comments": "合成反馈样例" }],
  });
});
afterEach(cleanup);

async function prepareImport(source) {
  const notify = vi.fn();
  const onDraftChange = vi.fn();
  const user = userEvent.setup();
  render(
    <NewTaskPage
      notify={notify}
      onDraftChange={onDraftChange}
      onChanged={vi.fn()}
      onNavigate={vi.fn()}
    />,
  );
  await screen.findByRole("button", { name: "上传文件", exact: true });
  if (source === "mysql") {
    await screen.findByText("合成反馈样例");
    await user.click(screen.getByRole("button", { name: "准备分析" }));
  } else {
    await user.click(screen.getByRole("button", { name: "上传文件", exact: true }));
    await user.click(screen.getByRole("button", { name: "选择文件" }));
    await user.upload(
      document.querySelector('input[type="file"]'),
      new File(["synthetic"], "SYNTHETIC.csv"),
    );
    await user.click(screen.getByRole("button", { name: "检查文件" }));
    await user.click(await screen.findByRole("button", { name: "导入并分析本批" }));
  }
  return { user, notify, onDraftChange };
}

test.each(["upload", "mysql"])(
  "%s导入成功后列表读取失败仍选中来源，重试只读取列表",
  async (source) => {
    apiMock.dataVersions
      .mockResolvedValueOnce([product])
      .mockRejectedValueOnce(new Error("合成列表503"));
    const { user, notify, onDraftChange } = await prepareImport(source);
    await screen.findByText("数据已导入，列表暂未刷新");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText(/请重新检查文件后重试/)).not.toBeInTheDocument();
    expect(notify).toHaveBeenCalledWith(
      source === "mysql"
        ? "数据库退货明细已导入并自动选中"
        : "用户反馈数据已导入并自动选中",
    );
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining("失效"), "error");
    expect(onDraftChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        resumePreflight: true,
        form: expect.objectContaining({ dataset_version_id: "import-v1" }),
      }),
    );
    await screen.findByText("合成预检检查点");
    expect(apiMock.preflightTask).toHaveBeenCalledWith(
      expect.objectContaining({ dataset_version_id: "import-v1" }),
    );

    let completeRefresh;
    apiMock.dataVersions.mockImplementationOnce(
      () => new Promise((resolve) => (completeRefresh = resolve)),
    );
    await user.click(screen.getByRole("button", { name: "重试刷新" }));
    expect(screen.getByRole("button", { name: "正在刷新…" })).toBeDisabled();
    completeRefresh([product, refreshedVersion]);
    await waitFor(() =>
      expect(screen.queryByText("数据已导入，列表暂未刷新")).not.toBeInTheDocument(),
    );
    expect(apiMock.dataVersions).toHaveBeenCalledTimes(3);
    expect(
      apiMock[source === "mysql" ? "importMysqlReturns" : "importReturns"],
    ).toHaveBeenCalledTimes(1);
    expect(apiMock.inspectReturnImport).toHaveBeenCalledTimes(
      source === "mysql" ? 0 : 1,
    );
    expect(apiMock.preflightTask).toHaveBeenCalledTimes(1);
  },
);

test("复用批次按返回version_id选中精确版本，不借用当前版本记录数", async () => {
  apiMock.importReturns.mockResolvedValue({
    ...importResult,
    duplicate: true,
    dataset: {
      ...importedDataset,
      current_version: 2,
      versions: [
        { ...importedVersion, id: "import-v2", row_count: 99 },
        importedVersion,
      ],
    },
  });
  apiMock.dataVersions
    .mockResolvedValueOnce([product])
    .mockRejectedValueOnce(new Error("合成列表503"));
  const { user, notify } = await prepareImport("upload");
  await screen.findByText("数据已导入，列表暂未刷新");
  await user.click(screen.getByRole("button", { name: "查看或修改数据" }));
  expect(screen.getByText("已导入批次 · 直接复用 · 2 条记录")).toBeVisible();
  expect(notify).toHaveBeenCalledWith("文件已导入过，已直接复用现有数据");
});

test("导入请求本身失败仍保留文件检查和错误，不选中来源", async () => {
  apiMock.importReturns.mockRejectedValue(new Error("合成导入503"));
  const { onDraftChange } = await prepareImport("upload");
  await screen.findByText("合成导入503 请重新检查文件后重试。");
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(apiMock.dataVersions).toHaveBeenCalledTimes(1);
  expect(onDraftChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      form: expect.objectContaining({ dataset_version_id: "" }),
    }),
  );
});

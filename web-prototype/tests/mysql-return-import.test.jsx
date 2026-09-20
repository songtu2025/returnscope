import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    mysqlReturnSchema: vi.fn(),
    previewMysqlReturns: vi.fn(),
    importMysqlReturns: vi.fn(),
    dataVersions: vi.fn(),
    configs: vi.fn(),
    status: vi.fn(),
    preflightTask: vi.fn(),
    qualityPreflight: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({ api: apiMock }));

import { MysqlReturnImportForm } from "../src/features/task-create/MysqlReturnImportForm";
import { NewTaskPage } from "../src/features/task-create/NewTaskPage";

const schema = {
  configured: true,
  database: "test_returns",
  table: "sale_return_order",
  max_rows: 100000,
  fields: [
    { name: "sku", label: "SKU / MSKU", required: true },
    { name: "customer-comments", label: "客户评论", required: true },
    { name: "店铺/站点", label: "店铺/站点", required: false },
  ],
  columns: ["msku", "customer_comments", "store"].map((name) => ({
    name,
    type: "varchar",
  })),
  mapping: {
    sku: "msku",
    "customer-comments": "customer_comments",
    "店铺/站点": "store",
  },
};
const preview = {
  row_count: 1,
  over_limit: false,
  rows: [{ sku: "SKU-1", "customer-comments": "尺码偏小", "店铺/站点": "测试店铺:US" }],
};

beforeEach(() => {
  vi.resetAllMocks();
  apiMock.mysqlReturnSchema.mockResolvedValue(schema);
  apiMock.previewMysqlReturns.mockResolvedValue(preview);
  apiMock.importMysqlReturns.mockResolvedValue({ version_id: "mysql-v1" });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function ImportView(props) {
  const [state, setState] = useState({});
  return (
    <>
      <MysqlReturnImportForm {...props} onStateChange={setState} />
      <button
        type="submit"
        form="mysql-prepare-form"
        disabled={!state.ready || Boolean(state.busy)}
      >
        准备分析
      </button>
    </>
  );
}

test("自动预览后准备分析，筛选修改立即使旧范围失效", async () => {
  const user = userEvent.setup();
  const onDone = vi.fn();
  render(<ImportView onDone={onDone} />);
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
  await screen.findByText("尺码偏小");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "准备分析" })).toBeEnabled(),
  );
  await user.click(screen.getByText("指定商品"));
  await user.type(screen.getByLabelText("SKU / MSKU（精确匹配）"), "SKU-1");
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
  await screen.findByText("尺码偏小");
  await user.click(screen.getByRole("button", { name: "准备分析" }));
  expect(apiMock.importMysqlReturns).toHaveBeenCalledWith(
    expect.objectContaining({ sku: "SKU-1", mapping: schema.mapping }),
  );
  await waitFor(() => expect(onDone).toHaveBeenCalledWith({ version_id: "mysql-v1" }));
});

test.each([
  ["近7天", "2024-02-24", "2024-03-01"],
  ["近30天", "2024-02-01", "2024-03-01"],
  ["本月至今", "2024-03-01", "2024-03-01"],
  ["上月", "2024-02-01", "2024-02-29"],
])("日期%s自动更新预览并正确处理跨月", async (label, start, end) => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2024, 2, 1, 0, 30));
  const user = userEvent.setup();
  render(<ImportView onDone={vi.fn()} />);
  await user.click(await screen.findByText("反馈日期", { exact: true }));
  await user.click(screen.getByRole("button", { name: label, exact: true }));
  expect(screen.getByLabelText("开始日期")).toHaveValue(start);
  expect(screen.getByLabelText("结束日期")).toHaveValue(end);
  await screen.findByText("尺码偏小");
  expect(apiMock.previewMysqlReturns).toHaveBeenLastCalledWith(
    expect.objectContaining({ date_from: start, date_to: end }),
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});

test("反向日期不发请求，开放日期范围保留其他筛选", async () => {
  const user = userEvent.setup();
  render(
    <ImportView
      onDone={vi.fn()}
      draft={{
        date_from: "2026-08-01",
        date_to: "2026-08-31",
        store: "测试店铺:US",
        sku: "SKU-1",
      }}
    />,
  );
  await screen.findByText("尺码偏小");
  fireEvent.change(screen.getByLabelText("开始日期"), {
    target: { value: "2026-09-01" },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("开始日期不能晚于结束日期");
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
  expect(apiMock.previewMysqlReturns).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText("结束日期"), { target: { value: "" } });
  await screen.findByText("尺码偏小");
  expect(apiMock.previewMysqlReturns).toHaveBeenLastCalledWith(
    expect.objectContaining({
      date_from: "2026-09-01",
      date_to: null,
      store: "测试店铺:US",
      sku: "SKU-1",
    }),
    expect.anything(),
  );
  await user.click(screen.getByText(/2026-09-01 — 不限结束/));
  await user.click(screen.getByRole("button", { name: "不限日期" }));
  await screen.findByText("尺码偏小");
  expect(apiMock.previewMysqlReturns).toHaveBeenLastCalledWith(
    expect.objectContaining({ date_from: null, date_to: null }),
    expect.anything(),
  );
});

test("过期预览即使较晚返回也不能覆盖新筛选", async () => {
  let resolveOld;
  apiMock.previewMysqlReturns.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
  );
  render(<ImportView onDone={vi.fn()} />);
  await waitFor(() => expect(apiMock.previewMysqlReturns).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText("SKU / MSKU（精确匹配）"), {
    target: { value: "NEW" },
  });
  await screen.findByText("尺码偏小");
  resolveOld({ ...preview, rows: [{ sku: "过期商品" }] });
  await waitFor(() => expect(screen.queryByText("过期商品")).not.toBeInTheDocument());
  expect(apiMock.previewMysqlReturns.mock.calls[0][1].signal.aborted).toBe(true);
});

test.each([
  [{ ...preview, row_count: 0, rows: [] }, "没有符合条件"],
  [{ ...preview, row_count: 100001, over_limit: true }, "请缩小筛选范围"],
  [{ ...preview, missing_store_rows: 1 }, "缺少店铺/站点映射"],
])("空数据、超量或店铺缺失时不允许准备分析", async (result, message) => {
  apiMock.previewMysqlReturns.mockResolvedValue(result);
  render(<ImportView onDone={vi.fn()} />);
  await screen.findByText(new RegExp(message));
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
});

test("预览失败可重试，刷新字段保留范围并重新预览", async () => {
  const user = userEvent.setup();
  apiMock.previewMysqlReturns.mockRejectedValueOnce(new Error("连接中断"));
  render(
    <ImportView onDone={vi.fn()} draft={{ date_from: "2026-08-01", sku: "SKU-1" }} />,
  );
  await screen.findByText("连接中断");
  await user.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("尺码偏小");
  await user.click(screen.getByText("数据连接与字段 · 已就绪"));
  await user.click(screen.getByRole("button", { name: "刷新店铺与字段" }));
  await waitFor(() => expect(apiMock.mysqlReturnSchema).toHaveBeenCalledTimes(2));
  expect(apiMock.mysqlReturnSchema).toHaveBeenLastCalledWith(
    expect.objectContaining({ refresh: true }),
  );
  expect(screen.getByLabelText("开始日期")).toHaveValue("2026-08-01");
  expect(screen.getByLabelText("SKU / MSKU（精确匹配）")).toHaveValue("SKU-1");
  await screen.findByText("尺码偏小");
});

test("字段缺失时先补充固定店铺，未配置时提示连接设置", async () => {
  apiMock.mysqlReturnSchema.mockResolvedValueOnce({
    ...schema,
    mapping: { ...schema.mapping, "店铺/站点": "" },
  });
  const view = render(<ImportView onDone={vi.fn()} />);
  const fixed = await screen.findByLabelText("固定店铺/站点 *");
  expect(apiMock.previewMysqlReturns).not.toHaveBeenCalled();
  fireEvent.change(fixed, { target: { value: "测试店铺:US" } });
  await screen.findByText("尺码偏小");
  view.unmount();
  apiMock.mysqlReturnSchema.mockResolvedValueOnce({ configured: false });
  render(<ImportView onDone={vi.fn()} />);
  await screen.findByText(/MySQL 数据源尚未配置/);
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
});

test("数据库导入使用用户反馈用语并保留来源字段映射", async () => {
  render(<ImportView onDone={vi.fn()} />);

  const table = await screen.findByRole("table", { name: "用户反馈数据样例" });
  for (const heading of ["反馈日期", "来源原因", "反馈原文"]) {
    expect(within(table).getByRole("columnheader", { name: heading })).toBeVisible();
  }
  await userEvent.click(screen.getByText("数据连接与字段 · 已就绪"));
  expect(screen.getByLabelText("客户评论字段映射")).toBeVisible();
});

test("数据库准备后在原页预检，修改范围会退出准备状态", async () => {
  const user = userEvent.setup();
  const product = {
    kind: "products",
    version_id: "product-v1",
    row_count: 1,
    dataset_name: "产品信息",
  };
  const imported = {
    kind: "returns",
    version_id: "mysql-v1",
    row_count: 1,
    dataset_name: "数据库退货明细",
    usage_scope: "task_input",
  };
  apiMock.dataVersions
    .mockResolvedValueOnce([product])
    .mockResolvedValue([product, imported]);
  apiMock.status.mockResolvedValue({});
  apiMock.configs.mockResolvedValue([
    {
      id: "conn-1",
      name: "测试模型",
      active_version: { id: "config-v1", primary_model: "test-model" },
    },
  ]);
  apiMock.preflightTask.mockRejectedValue(new Error("计划验证检查点"));
  apiMock.qualityPreflight.mockResolvedValue({});
  render(<NewTaskPage notify={vi.fn()} onChanged={vi.fn()} onNavigate={vi.fn()} />);
  await screen.findByText("尺码偏小");
  expect(await screen.findByText("已选 1 条用户反馈")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "准备分析" }));
  await screen.findByText("计划验证检查点");
  expect(apiMock.preflightTask).toHaveBeenCalledWith(
    expect.objectContaining({
      dataset_version_id: "mysql-v1",
      product_version_id: "product-v1",
    }),
  );
  expect(screen.getByLabelText("任务名称")).toBeVisible();
  expect(screen.queryByRole("group", { name: "数据来源" })).not.toBeInTheDocument();
  const confirmation = screen.getByRole("region", { name: "确认并开始分析" });
  expect(within(confirmation).getByLabelText("任务名称")).toBeVisible();
  expect(within(confirmation).getByRole("button", { name: "开始分析" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "查看或修改数据" }));
  expect(screen.getByRole("group", { name: "数据来源" })).toBeVisible();
  expect(apiMock.preflightTask).toHaveBeenCalledOnce();
  fireEvent.change(screen.getByLabelText("SKU / MSKU（精确匹配）"), {
    target: { value: "NEW" },
  });
  expect(screen.queryByText("计划验证检查点")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("任务名称")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "准备分析" })).toBeDisabled();
});

test("样例分页与详情不改变导入范围", async () => {
  const user = userEvent.setup();
  const rows = Array.from({ length: 6 }, (_, index) => ({
    ...preview.rows[0],
    sku: `商品-${index + 1}`,
    "order-id": `订单-${index + 1}`,
  }));
  apiMock.mysqlReturnSchema.mockResolvedValue({
    ...schema,
    fields: [...schema.fields, { name: "order-id", label: "订单号" }],
  });
  apiMock.previewMysqlReturns.mockResolvedValue({ ...preview, row_count: 123, rows });
  render(<ImportView onDone={vi.fn()} />);
  await screen.findByText("商品-1");
  await user.click(screen.getByRole("button", { name: "查看第1条详情" }));
  expect(screen.getByText("订单-1")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "下一页", exact: true }));
  expect(screen.getByText("商品-6")).toBeVisible();
  expect(screen.queryByText("订单-1")).not.toBeInTheDocument();
  expect(apiMock.previewMysqlReturns).toHaveBeenCalledTimes(1);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "准备分析" })).toBeEnabled(),
  );
});

import { apiMock, executionPlan } from "./product-flow-mocks";
import { expect, test, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewTaskPage } from "../src/features/task-create/NewTaskPage";
import { renderWithServerState as render } from "./renderWithServerState";

function setup() {
  apiMock.dataVersions.mockResolvedValue([
    {
      kind: "products",
      version_id: "products-v1",
      dataset_name: "合成产品",
      row_count: 2,
    },
    {
      kind: "returns",
      usage_scope: "task_input",
      version_id: "returns-v1",
      dataset_name: "合成反馈",
      row_count: 12,
    },
  ]);
  apiMock.configs.mockResolvedValue([
    {
      id: "conn",
      name: "合成连接",
      active_version: {
        id: "cfg",
        connection_id: "conn",
        primary_model: "model",
        primary_effort: "medium",
      },
      models: [
        {
          id: "model",
          model_key: "model",
          display_name: "合成模型",
          active: true,
          validation_status: "validated",
          supported_efforts: ["medium"],
        },
      ],
    },
  ]);
  apiMock.createTask.mockResolvedValue({ id: "created" });
  apiMock.preflightTask.mockResolvedValue({
    ...executionPlan,
    segments: [
      { ...executionPlan.segments[0], unique_comments: 3, record_count: 5 },
      {
        ...executionPlan.segments[0],
        segment_key: "second",
        scope: { store: "SEEKWAY:US", listing: "SK002" },
        unique_comments: 5,
        record_count: 7,
      },
    ],
  });
  const onNavigate = vi.fn();
  render(
    <NewTaskPage
      notify={vi.fn()}
      onChanged={vi.fn()}
      onNavigate={onNavigate}
      draft={{
        resumePreflight: true,
        dataEntryMode: "upload",
        form: { dataset_version_id: "returns-v1" },
      }}
    />,
  );
  return { onNavigate };
}

test("默认全选、取消单项联动数量与启动参数，排序及模型编辑保留选择", async () => {
  const user = userEvent.setup();
  const { onNavigate } = setup();
  expect(
    await screen.findByText("已选 2 / 2 个 Listing · 8 组待分析评论"),
  ).toBeVisible();
  await user.click(screen.getByRole("checkbox", { name: "参与分析：SK001" }));
  expect(screen.getByText("已选 1 / 2 个 Listing · 5 组待分析评论")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "全部参与分析" }).indeterminate).toBe(
    true,
  );
  const launch = screen.getByRole("button", { name: "创建并启动" });
  expect(launch).toBeEnabled();
  expect(screen.queryByLabelText(/我确认本次仅分析/)).not.toBeInTheDocument();
  expect(screen.getByText("本次分析 1 个 Listing · 5 组评论")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  await user.click(screen.getByRole("button", { name: "置顶 SK002" }));
  await user.type(screen.getByLabelText("任务名称"), "范围合成任务");
  await user.click(screen.getByLabelText("分析设置"));
  await user.clear(screen.getByLabelText(/^本次初筛抽检比例/));
  await user.type(screen.getByLabelText(/^本次初筛抽检比例/), "12");
  expect(screen.getByRole("checkbox", { name: "参与分析：SK001" })).not.toBeChecked();
  await user.click(launch);
  await waitFor(() => expect(apiMock.createTask).toHaveBeenCalledOnce());
  expect(onNavigate).toHaveBeenCalledWith("tasks", { kind: "task", id: "created" });
  expect(apiMock.createTask).toHaveBeenCalledWith(
    expect.objectContaining({
      selected_segment_keys: ["second"],
      segment_order: ["second", "footwear"],
    }),
  );
});

test("取消全部禁用启动，重新全选恢复数量；提交中锁定选择", async () => {
  const user = userEvent.setup();
  setup();
  const all = await screen.findByRole("checkbox", { name: "全部参与分析" });
  await user.click(all);
  expect(screen.getByText("已选 0 / 2 个 Listing · 0 组待分析评论")).toBeVisible();
  expect(screen.getByRole("button", { name: "没有可执行评论" })).toBeDisabled();
  expect(apiMock.createTask).not.toHaveBeenCalled();
  await user.click(all);
  expect(screen.getByText("已选 2 / 2 个 Listing · 8 组待分析评论")).toBeVisible();
  apiMock.createTask.mockReturnValue(new Promise(() => {}));
  await user.click(screen.getByRole("button", { name: "创建并启动" }));
  expect(all).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "参与分析：SK002" })).toBeDisabled();
});

test("同一Listing不同品类作为整体选择；创建失败保留已选范围", async () => {
  const user = userEvent.setup();
  setup();
  apiMock.preflightTask.mockResolvedValue({
    ...executionPlan,
    segments: [
      { ...executionPlan.segments[0], unique_comments: 3 },
      {
        ...executionPlan.segments[0],
        segment_key: "other-category",
        unique_comments: 5,
      },
    ],
  });
  await screen.findByText("已选 1 / 1 个 Listing · 8 组待分析评论");
  await user.click(screen.getAllByRole("checkbox", { name: "参与分析：SK001" })[0]);
  expect(
    screen
      .getAllByRole("checkbox", { name: "参与分析：SK001" })
      .every((item) => !item.checked),
  ).toBe(true);
  await user.click(screen.getByRole("checkbox", { name: "全部参与分析" }));
  apiMock.createTask.mockRejectedValue(new Error("合成失败"));
  await user.click(screen.getByRole("button", { name: "创建并启动" }));
  await screen.findByText("合成失败");
  expect(screen.getByRole("checkbox", { name: "全部参与分析" })).toBeChecked();
});

test("明细计划失效可重新检查，保留有效选择和顺序，不自动勾选新增Listing", async () => {
  const user = userEvent.setup();
  setup();
  await screen.findByText("已选 2 / 2 个 Listing · 8 组待分析评论");
  await user.click(screen.getByRole("checkbox", { name: "参与分析：SK001" }));
  await user.click(screen.getByRole("button", { name: "调整执行顺序" }));
  await user.click(screen.getByRole("button", { name: "置顶 SK002" }));
  const original = await apiMock.preflightTask.mock.results[0].value;
  apiMock.preflightTask.mockResolvedValue({
    ...original,
    plan_hash: "b".repeat(64),
    record_count: 14,
    unique_comment_count: 10,
    executable_count: 10,
    segments: [
      ...original.segments,
      {
        ...original.segments[1],
        segment_key: "new",
        scope: { store: "SEEKWAY:US", listing: "SK003" },
        unique_comments: 2,
        record_count: 2,
      },
    ],
  });
  apiMock.previewTaskSegment.mockRejectedValue(
    Object.assign(new Error("执行计划已变化"), { status: 409 }),
  );
  const row = screen.getByRole("heading", { name: "SK002" }).closest("tr");
  await user.click(within(row).getByRole("button", { name: "查看数据" }));
  await screen.findByText("执行计划已变化");
  await user.click(screen.getByRole("button", { name: "重新检查数据" }));
  expect(
    await screen.findByText("已选 1 / 3 个 Listing · 5 组待分析评论"),
  ).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "参与分析：SK001" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "参与分析：SK003" })).not.toBeChecked();
  expect(document.querySelector(".plan-segments tbody h4")).toHaveTextContent("SK002");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(apiMock.createTask).not.toHaveBeenCalled();
});

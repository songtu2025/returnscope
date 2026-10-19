import { afterEach, expect, test, vi } from "vitest";
import { cleanup, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { ResultDetailRecords } from "../src/features/classification-results/ResultDetailRecords";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import {
  clearResultRecordConditions,
  resultRecordConditions,
} from "../src/features/classification-results/resultRecordConditions";

afterEach(cleanup);
const query = {
  result_version_id: "version-one",
  q: "结果池筛选",
  page: "3",
  quality_status: "ready",
  selection_token: "selection",
  task_id: "source-task",
  task_return: "#analysis-tasks?q=来源",
  dashboard_return: "#analysis-dashboards?id=board",
  record_page: "2",
};
const fields = [
  ["problem", "FIT", "问题：FIT"],
  ["product_name", "合成产品", "产品名称：合成产品"],
  ["product_sku", "SKU-101", "产品SKU：SKU-101"],
  ["order_id", "NO-MATCH", "订单号：NO-MATCH"],
  ["record_quality_status", "review_required", "结果状态：需复核"],
  ["comment_status", "NEGATIVE", "语义类型：仅负向"],
  ["system_rerun_required", "false", "重跑标记：无需重跑"],
];
const cleared = {
  problem: "",
  productName: "",
  productSku: "",
  orderId: "",
  recordQualityStatus: "",
  commentStatus: "",
  systemRerunRequired: "",
  recordPage: 1,
};

function setup(conditions) {
  const route = classificationResultRouteState({ ...query, ...conditions });
  const updateRoute = vi.fn();
  render(
    <ResultDetailRecords
      route={route}
      updateRoute={updateRoute}
      result={{ analysis_context: "user_feedback" }}
      isUserFeedback
      records={{ items: [], total: 0 }}
      recordsLoading={false}
      recordsError=""
      orderInput={route.orderId}
      setOrderInput={vi.fn()}
    />,
  );
  return { route, updateRoute };
}

test.each(fields)("单项条件 %s 能显示并就地清除", async (key, value, label) => {
  const { route, updateRoute } = setup({ [key]: value });
  expect(screen.getByLabelText("生效记录条件")).toHaveTextContent(label);
  const button = screen.getByRole("button", { name: "清除条件并显示全部记录" });
  button.focus();
  await userEvent.keyboard("{Enter}");
  expect(updateRoute).toHaveBeenCalledExactlyOnceWith(cleared);
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
  expect({ ...route, ...updateRoute.mock.calls[0][0] }).toMatchObject({
    version: "version-one",
    q: query.q,
    page: 3,
    qualityStatus: "ready",
    selectionToken: "selection",
    taskId: "source-task",
    taskReturn: query.task_return,
    dashboardReturn: query.dashboard_return,
  });
});

test("组合条件完整显示，工具栏与空态复用相同清除范围", async () => {
  const { route, updateRoute } = setup(
    Object.fromEntries(fields.map(([key, value]) => [key, value])),
  );
  expect(resultRecordConditions(route)).toEqual(fields.map(([, , label]) => label));
  await userEvent.click(
    within(screen.getByRole("group", { name: "结果筛选" })).getByRole("button", {
      name: "清除记录条件",
    }),
  );
  expect(updateRoute).toHaveBeenCalledWith(cleared);
  clearResultRecordConditions(updateRoute);
  expect(updateRoute.mock.calls[0]).toEqual(updateRoute.mock.calls[1]);
});

test("只有结果池筛选时不显示记录清除空态入口", () => {
  setup({});
  expect(screen.getByRole("button", { name: "清除记录条件" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "清除条件并显示全部记录" })).toBeNull();
  expect(screen.getByText("此结果版本暂无记录。")).toBeVisible();
});

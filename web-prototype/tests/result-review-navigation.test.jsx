import { cleanup, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";
import { buildHash, parseHash } from "../src/app/hashRouter";
import { classificationResultRouteState } from "../src/features/classification-results/classificationResultRoute";
import { renderWithServerState as render } from "./renderWithServerState";

const result = {
  version_id: "proof-result",
  version: 3,
  listing: "合成 Listing",
  store_site: "合成店铺",
  publish_status: "published",
  record_count: 3,
  unit_count: 3,
  analysis_context: "user_feedback",
};
const record = {
  source_record_id: "source-one",
  source_row: 1,
  order_id: "synthetic-order",
  return_date: "2026-10-19",
  comment: "合成反馈",
  quality_status: "review_required",
  processing_status: "MANUAL_REVIEW",
  classification: { semantic_units: [] },
};
const groups = {
  items: [{ record, member_count: 1, members: [record] }],
  total: 1,
  source_total: 2,
  page: 1,
  page_size: 20,
};
const summary = {
  version_id: result.version_id,
  quality: [{ quality_status: "review_required", record_count: 2, unit_count: 1 }],
  processing_statuses: [],
  top_problems: [],
};
const query = {
  result_version_id: result.version_id,
  task_id: "source-task",
  task_return: "#analysis-tasks?task_id=source-task&q=保留",
  dashboard_return: "#analysis-dashboards?dashboard_id=board&version_id=frozen",
  q: "结果池查询",
  selection_token: "pool-selection",
  problem: "原问题",
  product_name: "原产品",
  product_sku: "原SKU",
  order_id: "原订单",
  comment_status: "NEGATIVE",
  system_rerun_required: "true",
  record_page: 4,
};
beforeEach(() => {
  window.history.replaceState({}, "", "/" + buildHash("classification-results", query));
  vi.spyOn(api, "classificationResult").mockResolvedValue(result);
  vi.spyOn(api, "classificationResultSummary").mockResolvedValue(summary);
  vi.spyOn(api, "classificationResultRecordGroups").mockResolvedValue(groups);
  vi.spyOn(api, "classificationResultDrilldown").mockResolvedValue({
    items: [],
    total: 0,
  });
  vi.spyOn(api, "classificationResultVersions").mockResolvedValue([result]);
  vi.spyOn(api, "correctClassificationResult");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const open = () =>
  render(<ClassificationResultsPage userId="proof-user" notify={vi.fn()} />);

test("键盘点击摘要后清除无关条件、筛选待复核、定位记录，保留固定版本和来源", async () => {
  open();
  const button = await screen.findByRole("button", {
    name: "查看此版本全部需复核记录",
  });
  button.focus();
  await userEvent.keyboard("{Enter}");
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
  expect(parseHash().query).toMatchObject({
    result_version_id: query.result_version_id,
    task_id: query.task_id,
    task_return: query.task_return,
    dashboard_return: query.dashboard_return,
    q: query.q,
    selection_token: query.selection_token,
    record_quality_status: "review_required",
  });
  expect(classificationResultRouteState(parseHash().query).recordPage).toBe(1);
  for (const field of [
    "problem",
    "product_name",
    "product_sku",
    "order_id",
    "comment_status",
    "system_rerun_required",
  ]) {
    expect(parseHash().query[field]).toBeUndefined();
  }
  expect(api.classificationResultRecordGroups).toHaveBeenLastCalledWith(
    result.version_id,
    expect.objectContaining({
      page: 1,
      quality_status: "review_required",
      problem: "",
      product_name: "",
      product_sku: "",
      order_id: "",
      comment_status: "",
    }),
    expect.any(Object),
  );
  expect(screen.getByRole("textbox", { name: "搜索 order-id" })).toHaveValue("");
  expect(api.correctClassificationResult).not.toHaveBeenCalled();
});

test("已经位于待复核范围时再次点击仍可定位记录区", async () => {
  window.history.replaceState(
    {},
    "",
    "/" +
      buildHash("classification-results", {
        result_version_id: result.version_id,
        record_quality_status: "review_required",
      }),
  );
  open();
  const button = await screen.findByRole("button", {
    name: "查看此版本全部需复核记录",
  });
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
  await userEvent.click(button);
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
});

test("待复核为零时保留统计并禁用快捷入口", async () => {
  vi.mocked(api.classificationResultSummary).mockResolvedValue({
    ...summary,
    quality: [],
  });
  open();
  const button = await screen.findByRole("button", {
    name: "查看此版本全部需复核记录",
  });
  expect(button).toBeDisabled();
  expect(button).toHaveTextContent("0");
});

test("筛选读取未完成时不提前移动焦点，完成后聚焦记录区", async () => {
  let finish;
  vi.mocked(api.classificationResultRecordGroups).mockImplementation((_id, filters) =>
    filters.quality_status === "review_required"
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : Promise.resolve(groups),
  );
  open();
  await userEvent.click(
    await screen.findByRole("button", { name: "查看此版本全部需复核记录" }),
  );
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  expect(screen.getByRole("region", { name: "用户反馈记录" })).not.toHaveFocus();
  await act(async () => finish(groups));
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
});

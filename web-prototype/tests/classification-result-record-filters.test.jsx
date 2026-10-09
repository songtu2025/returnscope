import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResultRecordGroups: vi.fn(),
    classificationResultDrilldown: vi.fn(),
  },
}));
vi.mock("../src/api", () => ({ api: apiMock }));

import { useHashRoute } from "../src/app/hashRouter";
import {
  classificationResultRouteState,
  writeClassificationResultRoute,
} from "../src/features/classification-results/classificationResultRoute";
import { ResultDetailRecords } from "../src/features/classification-results/ResultDetailRecords";
import { ResultRecordRow } from "../src/features/classification-results/ClassificationResultDetailParts";
import { useClassificationResultRecords } from "../src/features/classification-results/useClassificationResultRecords";
import { renderWithServerState as render } from "./renderWithServerState";

function RecordFiltersHarness({ notify = vi.fn() }) {
  const { route: hashRoute } = useHashRoute();
  const route = classificationResultRouteState(hashRoute.query);
  const state = useClassificationResultRecords({ route, notify });
  const [orderInput, setOrderInput] = useState(route.orderId);
  const updateRoute = (changes) =>
    writeClassificationResultRoute({ ...route, ...changes });
  return (
    <ResultDetailRecords
      {...state}
      route={route}
      updateRoute={updateRoute}
      result={{ analysis_context: "user_feedback" }}
      isUserFeedback
      orderInput={orderInput}
      setOrderInput={setOrderInput}
      totalPages={Math.max(Math.ceil((state.records?.total || 0) / route.pageSize), 1)}
      changeRecordPage={(recordPage) => updateRoute({ recordPage })}
      changePageSize={(pageSize) => updateRoute({ pageSize, recordPage: 1 })}
    />
  );
}

beforeEach(() => {
  window.location.hash = "classification-results?result_version_id=synthetic-version";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [],
    total: 0,
    source_total: 0,
    page: 1,
    page_size: 20,
  });
  apiMock.classificationResultDrilldown.mockResolvedValue({ items: [] });
});
afterEach(cleanup);

test("已忽略记录的行内状态与筛选选项一致", () => {
  render(
    <ResultRecordRow
      group={{
        record: { quality_status: "excluded", comment_summary_status: "NO_CONFIRMED" },
        member_count: 1,
        members: [],
      }}
      analysisContext="user_feedback"
      onOpen={() => {}}
    />,
  );
  expect(
    screen.getByText("已忽略", { selector: ".result-quality-badge" }),
  ).toBeVisible();
  expect(screen.queryByText("状态未提供")).not.toBeInTheDocument();
});

test("两个筛选器提供与记录标签相同的完整状态选项", async () => {
  render(<RecordFiltersHarness />);
  await screen.findByText("当前条件没有反馈记录");
  expect(
    within(screen.getByLabelText("结果状态"))
      .getAllByRole("option")
      .map((el) => el.textContent),
  ).toEqual(["全部状态", "可用", "需复核", "不可用", "已忽略"]);
  expect(
    within(screen.getByLabelText("语义类型"))
      .getAllByRole("option")
      .map((el) => el.textContent),
  ).toEqual(["全部类型", "仅正向", "仅负向", "混合表现", "疑似冲突", "无确定评价"]);
  expect(screen.getByRole("button", { name: "清除结果筛选" })).toBeDisabled();
});

test("URL 恢复组合条件且版本质量筛选不会污染记录状态", async () => {
  window.location.hash =
    "classification-results?result_version_id=synthetic-version&quality_status=ready&record_quality_status=unusable&comment_status=NEGATIVE&record_page=2&page_size=50&problem=FIT&product_name=demo&product_sku=SKU&order_id=ORDER";
  render(<RecordFiltersHarness />);
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenCalledWith(
      "synthetic-version",
      {
        page: 2,
        page_size: 50,
        quality_status: "unusable",
        comment_status: "NEGATIVE",
        problem: "FIT",
        product_name: "demo",
        product_sku: "SKU",
        order_id: "ORDER",
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ),
  );
  expect(screen.getByLabelText("结果状态")).toHaveValue("unusable");
  expect(screen.getByLabelText("语义类型")).toHaveValue("NEGATIVE");
  expect(apiMock.classificationResultDrilldown).toHaveBeenCalledWith(
    "synthetic-version",
    "problem",
    { page: 1, page_size: 100 },
    expect.any(Object),
  );
});

test("筛选立即查询、重置页码且清除时保留其他条件", async () => {
  const user = userEvent.setup();
  window.location.hash =
    "classification-results?result_version_id=synthetic-version&record_page=3&order_id=ORDER&product_sku=SKU";
  render(<RecordFiltersHarness />);
  await screen.findByText("当前条件没有反馈记录");
  await user.selectOptions(screen.getByLabelText("结果状态"), "review_required");
  await user.selectOptions(screen.getByLabelText("语义类型"), "MIXED");
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
      "synthetic-version",
      expect.objectContaining({
        page: 1,
        quality_status: "review_required",
        comment_status: "MIXED",
        product_sku: "SKU",
        order_id: "ORDER",
      }),
      expect.any(Object),
    ),
  );
  await user.click(screen.getByRole("button", { name: "清除结果筛选" }));
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
      "synthetic-version",
      expect.objectContaining({
        page: 1,
        quality_status: "",
        comment_status: "",
        product_sku: "SKU",
        order_id: "ORDER",
      }),
      expect.any(Object),
    ),
  );
  expect(window.location.hash).not.toContain("record_page");
  expect(window.location.hash).not.toContain("comment_status");
  expect(screen.getByLabelText("语义类型")).toHaveValue("");
});

test("hash 历史变化同步筛选器和查询参数", async () => {
  render(<RecordFiltersHarness />);
  await screen.findByText("当前条件没有反馈记录");
  await act(async () => {
    window.location.hash =
      "classification-results?result_version_id=synthetic-version&record_quality_status=excluded&comment_status=NO_CONFIRMED";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(screen.getByLabelText("结果状态")).toHaveValue("excluded");
  expect(screen.getByLabelText("语义类型")).toHaveValue("NO_CONFIRMED");
  await waitFor(() =>
    expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
      "synthetic-version",
      expect.objectContaining({
        quality_status: "excluded",
        comment_status: "NO_CONFIRMED",
      }),
      expect.any(Object),
    ),
  );
});

test("查询失败保留条件并提供原条件重试", async () => {
  const notify = vi.fn();
  apiMock.classificationResultRecordGroups.mockRejectedValueOnce(
    new Error("合成请求失败"),
  );
  window.location.hash =
    "classification-results?result_version_id=synthetic-version&record_quality_status=unusable&comment_status=CONFLICT";
  render(<RecordFiltersHarness notify={notify} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("合成请求失败");
  expect(screen.getByLabelText("结果状态")).toHaveValue("unusable");
  expect(screen.getByLabelText("语义类型")).toHaveValue("CONFLICT");
  await userEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("当前条件没有反馈记录");
  expect(apiMock.classificationResultRecordGroups).toHaveBeenLastCalledWith(
    "synthetic-version",
    expect.objectContaining({ quality_status: "unusable", comment_status: "CONFLICT" }),
    expect.any(Object),
  );
});

test("筛选期间旧请求被取消，迟到响应不能覆盖新结果", async () => {
  let completeOld;
  apiMock.classificationResultRecordGroups.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        completeOld = resolve;
      }),
  );
  render(<RecordFiltersHarness />);
  await waitFor(() => expect(completeOld).toBeTypeOf("function"));
  const oldSignal = apiMock.classificationResultRecordGroups.mock.calls[0][2].signal;
  await userEvent.selectOptions(screen.getByLabelText("结果状态"), "unusable");
  await screen.findByText("当前条件没有反馈记录");
  expect(oldSignal.aborted).toBe(true);
  await act(async () => completeOld({ items: [], total: 99, source_total: 100 }));
  expect(screen.getByText("0 组反馈 · 关联0 条源明细")).toBeVisible();
});

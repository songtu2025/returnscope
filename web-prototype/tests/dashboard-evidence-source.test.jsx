import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";
import { buildHash, parseHash, useHashRoute } from "../src/app/hashRouter";
import { renderWithServerState as render } from "./renderWithServerState";

const result = {
  version_id: "historical-result",
  version: 2,
  listing: "合成 Listing",
  publish_status: "published",
  analysis_context: "user_feedback",
  record_count: 2,
  unit_count: 2,
};
const groups = ["target", "other"].map((source) => ({
  record: {
    id: source,
    source_record_id: source,
    result_version_id: result.version_id,
    order_id: "相同订单",
    comment: `合成反馈-${source}`,
    classification: {},
  },
  member_count: 1,
  members: [],
}));
const original =
  "#analysis-dashboards?dashboard=board&version=old-board&problem=FIT&record_page=3&subject=PRODUCT&product_sku=合成SKU&date_from=2026-01-01";
function SourceFlow() {
  const { route } = useHashRoute();
  return route.page === "classification-results" ? (
    <ClassificationResultsPage route={route} userId="proof-user" notify={vi.fn()} />
  ) : (
    <p>已返回原看板</p>
  );
}
beforeEach(() => {
  window.history.replaceState(
    {},
    "",
    buildHash("classification-results", {
      result_version_id: result.version_id,
      feedback_source_record_id: "target",
      dashboard_return: original,
    }),
  );
  vi.spyOn(api, "classificationResult").mockResolvedValue(result);
  vi.spyOn(api, "classificationResultSummary").mockResolvedValue({
    quality: [],
    processing_statuses: [],
    top_problems: [],
  });
  vi.spyOn(api, "classificationResultDrilldown").mockResolvedValue({
    items: [],
    total: 0,
  });
  vi.spyOn(api, "classificationResultRecordGroups").mockImplementation(
    async (_version, filters) => ({
      items: filters.feedback_source_record_id ? [groups[0]] : groups,
      total: filters.feedback_source_record_id ? 1 : 2,
      page: 1,
      page_size: 20,
    }),
  );
  vi.spyOn(api, "classificationResultVersions").mockResolvedValue([
    { ...result, version_id: "latest-result", version: 3 },
  ]);
  vi.spyOn(api, "correctClassificationResult");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("精确读取同订单中的目标反馈组，固定来源版本并聚焦记录区，返回恢复完整看板上下文", async () => {
  render(<SourceFlow />);
  expect(await screen.findByText("合成反馈-target")).toBeVisible();
  expect(screen.queryByText("合成反馈-other")).toBeNull();
  await waitFor(() =>
    expect(screen.getByRole("region", { name: "用户反馈记录" })).toHaveFocus(),
  );
  expect(api.classificationResultRecordGroups).toHaveBeenCalledWith(
    result.version_id,
    expect.objectContaining({ feedback_source_record_id: "target", page: 1 }),
    expect.any(Object),
  );
  expect(api.classificationResultVersions).not.toHaveBeenCalled();
  expect(screen.getByLabelText("生效记录条件")).toHaveTextContent(
    "来源定位：看板中的反馈组",
  );
  await userEvent.click(screen.getByRole("button", { name: "返回分析看板" }));
  expect(parseHash().query).toEqual(parseHash(original).query);
  expect(api.correctClassificationResult).not.toHaveBeenCalled();
});

test("清除来源定位后恢复此版本全部反馈，不携带过期源记录条件", async () => {
  render(<SourceFlow />);
  await screen.findByText("合成反馈-target");
  await userEvent.click(screen.getByRole("button", { name: "清除记录条件" }));
  expect(await screen.findByText("合成反馈-other")).toBeVisible();
  expect(parseHash().query.feedback_source_record_id).toBeUndefined();
  expect(parseHash().query.dashboard_return).toBe(original);
  expect(api.classificationResultRecordGroups.mock.calls.at(-1)[1]).not.toHaveProperty(
    "feedback_source_record_id",
  );
  expect(api.correctClassificationResult).not.toHaveBeenCalled();
});

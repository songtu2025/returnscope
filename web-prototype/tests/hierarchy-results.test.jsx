import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    classificationResult: vi.fn(),
    classificationResultSummary: vi.fn(),
    classificationResultRecordGroups: vi.fn(),
    classificationResultDrilldown: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    classificationResultVersions: vi.fn(),
    reviewBatches: vi.fn(),
  },
}));
vi.mock("../src/api", () => ({ api: apiMock }));

import { ClassificationResultsPage } from "../src/pages/ClassificationResultsPage";
import { ReturnReasonInsights } from "../src/features/analysis-dashboards/ReturnReasonInsights";
import { ReviewRecordRow } from "../src/features/review-batches/ReviewRecordComponents";
import { renderWithServerState as render } from "./renderWithServerState";

const hierarchy = Array.from({ length: 14 }, (_, index) => ({
  value: `CAT_${index}`,
  label_name: `分类${index}`,
  label_path: ["功能", `分类${index}`],
  record_count: 1,
  unit_count: 1,
}));
const leaf = {
  value: "COLD",
  label_name: "不保暖",
  label_path: ["功能", "保暖性", "不保暖"],
  record_count: 1,
};

beforeEach(() => {
  window.location.hash = "";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
});
afterEach(cleanup);

test("结果页保留全部层级节点并将父节点作为筛选编码", async () => {
  const user = userEvent.setup();
  const version = {
    version_id: "v2",
    result_id: "result",
    version: 1,
    quality_status: "ready",
    publish_status: "published",
    record_count: 1,
    unit_count: 1,
    product_names: [],
  };
  apiMock.classificationResult.mockResolvedValue(version);
  apiMock.classificationResultSummary.mockResolvedValue({
    quality: [{ quality_status: "ready", record_count: 1 }],
    hierarchy_problems: [...hierarchy, leaf],
  });
  apiMock.classificationResultRecordGroups.mockResolvedValue({
    items: [],
    total: 0,
    source_total: 0,
  });
  apiMock.classificationResultDrilldown.mockResolvedValue({ items: [] });
  apiMock.classificationResultVersions.mockResolvedValue([version]);
  apiMock.reviewBatches.mockResolvedValue({ items: [] });
  apiMock.classificationResultDownloadUrl.mockReturnValue("/download");
  render(
    <ClassificationResultsPage
      notify={vi.fn()}
      route={{ query: { result_version_id: "v2" } }}
    />,
  );
  const lastParent = await screen.findByRole("button", { name: /功能 → 分类13/ });
  expect(screen.getByRole("button", { name: /功能 → 保暖性 → 不保暖/ })).toBeVisible();
  await user.click(lastParent);
  await waitFor(() => expect(window.location.hash).toContain("problem=CAT_13"));
});

test("看板展示全部父级去重计数，只有末端进入原因诊断", async () => {
  const user = userEvent.setup();
  const updateRoute = vi.fn();
  render(
    <ReturnReasonInsights
      route={{}}
      updateRoute={updateRoute}
      data={{
        reasons: [{ value: "COLD", label: "不保暖", record_count: 1, percentage: 100 }],
        hierarchy_problems: [...hierarchy, leaf],
        taxonomy: {
          structure_version: 2,
          labels: [{ code: "COLD", name: "不保暖", label_path: leaf.label_path }],
        },
      }}
    />,
  );
  const reasons = screen.getByText("具体反馈原因").closest("section");
  expect(
    within(reasons).getByRole("button", {
      name: /功能 → 保暖性 → 不保暖.*1 · 100\.0%/,
    }),
  ).toBeVisible();
  const section = screen.getByRole("region", { name: "标签层级统计" });
  expect(section).toHaveClass("return-hierarchy-ranking");
  expect(within(section).getAllByRole("button")).toHaveLength(15);
  expect(
    within(section).getByRole("button", { name: "功能 → 分类13 1 条" }),
  ).toBeDisabled();
  await user.click(
    within(section).getByRole("button", { name: "功能 → 保暖性 → 不保暖 1 条" }),
  );
  expect(updateRoute).toHaveBeenCalledWith(
    { problem: "COLD", recordPage: 1 },
    { replace: true },
  );
});

test("复核记录优先展示所属版本的标签路径", () => {
  render(
    <ReviewRecordRow
      record={{
        classification: { primary_label_codes: ["COLD"] },
        problem_label_paths: { COLD: leaf.label_path },
        workflow_status: "pending",
      }}
    />,
  );
  expect(screen.getByText("功能 → 保暖性 → 不保暖")).toBeVisible();
  expect(screen.queryByText("COLD")).not.toBeInTheDocument();
});

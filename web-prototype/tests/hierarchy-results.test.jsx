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
import { ReturnReasonExplorerHierarchy } from "../src/features/analysis-dashboards/ReturnReasonExplorerHierarchy";
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

test("看板分类树默认收起，父级只展开，末端选择与榜单联动", async () => {
  const user = userEvent.setup();
  const updateRoute = vi.fn();
  const nodes = [
    { value: "FUNCTION", label_name: "功能", record_count: 3 },
    { value: "WARMTH", parent_code: "FUNCTION", label_name: "保暖性", record_count: 2 },
    { ...leaf, parent_code: "WARMTH" },
    { value: "HOT", parent_code: "FUNCTION", label_name: "过热", record_count: 1 },
  ];
  const props = {
    route: {},
    updateRoute,
    data: {
      reasons: [{ value: "COLD", label: "不保暖", record_count: 1, percentage: 100 }],
      selected_reason: {
        value: "COLD",
        label: "不保暖",
        record_count: 1,
        percentage: 100,
      },
      hierarchy_problems: nodes,
      taxonomy: {
        structure_version: 2,
        labels: [{ code: "COLD", name: "不保暖", label_path: leaf.label_path }],
      },
    },
  };
  const rendered = render(<ReturnReasonInsights {...props} />);
  const reasons = screen.getByText("具体反馈原因").closest("section");
  expect(
    within(reasons).getByRole("button", {
      name: /功能 → 保暖性 → 不保暖.*1 · 100\.0%/,
    }),
  ).toBeVisible();
  const toggle = screen.getByText("按分类层级查看");
  expect(toggle.closest("details")).not.toHaveAttribute("open");
  await user.click(toggle);
  const tree = screen.getByRole("list", { name: "分类层级" });
  const warmth = within(tree).getByText("保暖性").closest("details");
  expect(warmth).toHaveAttribute("open");
  await user.click(within(tree).getByText("保暖性"));
  expect(warmth).not.toHaveAttribute("open");
  expect(updateRoute).not.toHaveBeenCalled();
  await user.click(within(tree).getByText("保暖性"));
  await user.click(within(tree).getByRole("button", { name: "过热 1条" }));
  expect(updateRoute).toHaveBeenLastCalledWith(
    { problem: "HOT", recordPage: 1, reasonPage: 0 },
    { replace: true },
  );
  rendered.rerender(<ReturnReasonInsights {...props} route={{ subject: "PRODUCT" }} />);
  expect(screen.getByText("按分类层级查看").closest("details")).not.toHaveAttribute(
    "open",
  );
});

test.each([0, 1, 10, 11, 39])("分类树%s项全部可访问且不再分页", async (total) => {
  const user = userEvent.setup();
  render(
    <ReturnReasonExplorerHierarchy
      hierarchy={Array.from({ length: total }, (_, index) => ({
        ...leaf,
        value: `LEAF_${index}`,
      }))}
      selectedCode=""
      onUpdateRoute={vi.fn()}
    />,
  );
  if (total) {
    await user.click(screen.getByText("按分类层级查看"));
    expect(
      within(screen.getByRole("list", { name: "分类层级" })).getAllByRole("button"),
    ).toHaveLength(total);
  } else {
    expect(screen.queryByText("按分类层级查看")).not.toBeInTheDocument();
  }
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
});

test("切换选中原因会展开新路径，收起入口不被自动打开", async () => {
  const user = userEvent.setup();
  const nodes = [
    { value: "FUNCTION", label_name: "功能", record_count: 2 },
    { value: "WARMTH", parent_code: "FUNCTION", label_name: "保暖性", record_count: 1 },
    { ...leaf, parent_code: "WARMTH" },
    { value: "QUALITY", label_name: "质量", record_count: 1 },
    { value: "FAULT", parent_code: "QUALITY", label_name: "损坏", record_count: 1 },
  ];
  const props = { hierarchy: nodes, selectedCode: "FAULT", onUpdateRoute: vi.fn() };
  const rendered = render(<ReturnReasonExplorerHierarchy {...props} />);
  await user.click(screen.getByText("按分类层级查看"));
  const root = screen.getByText("按分类层级查看").closest("details");
  expect(screen.getByText("质量").closest("details")).toHaveAttribute("open");
  expect(screen.getByText("功能").closest("details")).not.toHaveAttribute("open");
  rendered.rerender(<ReturnReasonExplorerHierarchy {...props} selectedCode="COLD" />);
  expect(screen.getByText("功能").closest("details")).toHaveAttribute("open");
  expect(screen.getByText("保暖性").closest("details")).toHaveAttribute("open");
  expect(screen.getByRole("button", { name: "不保暖 1条" })).toHaveAttribute(
    "aria-current",
    "true",
  );
  await user.click(screen.getByText("按分类层级查看"));
  rendered.rerender(<ReturnReasonExplorerHierarchy {...props} />);
  expect(root).not.toHaveAttribute("open");
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

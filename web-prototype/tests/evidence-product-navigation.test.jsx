import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "../src/api";
import { renderWithServerState as render } from "./renderWithServerState";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";
import { DataAssetsPage } from "../src/features/data-management/DataAssetsPage";
import {
  buildHash,
  navigateHash,
  parseHash,
  useHashRoute,
} from "../src/app/hashRouter";
import {
  classificationResultRouteState,
  evidenceProductQuery,
  productResultReturnQuery,
} from "../src/features/classification-results/classificationResultRoute";

const source = {
  result_version_id: "historical-result",
  record_page: "4",
  page: "3",
  page_size: "50",
  problem: "FIT",
  store_site: "DEMO:US",
  listing: "DEMO",
  product_sku: "PRODUCT",
  record_quality_status: "review_required",
  dashboard_return: "#analysis-dashboards?dashboard=board&version=old",
};
const record = {
  id: "record",
  source_record_id: "source",
  result_version_id: source.result_version_id,
  product_match_status: "matched",
  matched_msku: "MATCHED",
  source_sku: "SOURCE",
  store_site: "DEMO:US",
  classification: {},
};
const dataset = {
  id: "products",
  kind: "products",
  current_version: 3,
  row_count: 2,
  schema: [],
};
const row = {
  _row_index: 1,
  MSKU: "MATCHED",
  "店铺/站点": "DEMO:US",
  Listing: "DEMO",
  产品名称: "合成产品",
};
function Harness() {
  const { route } = useHashRoute();
  if (route.page === "data-assets")
    return (
      <DataAssetsPage
        route={route}
        userId="proof-user"
        notify={vi.fn()}
        onNavigate={vi.fn()}
      />
    );
  const query = evidenceProductQuery(
    record,
    classificationResultRouteState(route.query),
  );
  return (
    <EvidenceDrawer
      group={{ record, member_count: 1, members: [] }}
      analysisContext="user_feedback"
      onClose={vi.fn()}
      onViewProduct={() => navigateHash("data-assets", query)}
      returnFocusRef={{ current: null }}
    />
  );
}
beforeEach(() => {
  window.history.replaceState({}, "", buildHash("classification-results", source));
  vi.spyOn(api, "datasets").mockResolvedValue([dataset]);
  vi.spyOn(api, "dataset").mockResolvedValue(dataset);
  vi.spyOn(api, "datasetRows").mockResolvedValue({
    records: [row],
    total: 1,
    facets: { stores: ["DEMO:US"], categories: [] },
  });
  vi.spyOn(api, "updateDatasetRow");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("匹配商品按MSKU及店铺读取当前资料，往返恢复原版本、条件和页码", async () => {
  render(<Harness />);
  await userEvent.click(screen.getByText("业务信息"));
  const open = screen.getByRole("button", { name: "查看产品资料" });
  open.focus();
  await userEvent.keyboard("{Enter}");
  await screen.findByText("MATCHED", { exact: true });
  expect(parseHash().query).toMatchObject({ rows_q: "MATCHED", rows_store: "DEMO:US" });
  expect(api.datasetRows).toHaveBeenCalledWith("products", "MATCHED", 0, 15, {
    store: "DEMO:US",
    category: "",
  });
  expect(parseHash().query.reference_version).toBeUndefined();
  await userEvent.click(screen.getByRole("button", { name: "返回分类结果" }));
  expect(parseHash().query).toEqual(source);
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
});

test("返回分类结果保留产品未保存输入，确认放弃后才离开", async () => {
  render(<Harness />);
  await userEvent.click(screen.getByText("业务信息"));
  await userEvent.click(screen.getByRole("button", { name: "查看产品资料" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "编辑 MATCHED 产品信息" }),
  );
  fireEvent.change(screen.getByLabelText("产品名称"), {
    target: { value: "未保存输入" },
  });
  fireEvent.click(screen.getByRole("button", { name: "返回分类结果" }));
  expect(parseHash().page).toBe("data-assets");
  expect(screen.getByLabelText("产品名称")).toHaveValue("未保存输入");
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("产品名称")).toHaveValue("未保存输入");
  fireEvent.click(screen.getByRole("button", { name: "返回分类结果" }));
  fireEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  await waitFor(() => expect(parseHash().query).toEqual(source));
  expect(api.updateDatasetRow).not.toHaveBeenCalled();
});

test.each([
  { product_match_status: "unmatched" },
  { matched_msku: "" },
  { store_site: "" },
])("匹配标识不足不猜测商品：%j", (changes) => {
  expect(
    evidenceProductQuery(
      { ...record, ...changes },
      classificationResultRouteState(source),
    ),
  ).toBeNull();
});
test.each([
  undefined,
  "#settings",
  "#classification-results",
  "#classification-results?version=v&view=reviews",
])("忽略不属于分类结果详情的返回地址：%s", (hash) => {
  expect(productResultReturnQuery(hash)).toBeNull();
});
test("返回仅还原浏览条件，不执行来源动作", () => {
  const result = productResultReturnQuery(
    buildHash("classification-results", {
      ...source,
      action: "review",
      unknown: "delete",
    }),
  );
  expect(result.action).toBe("");
  expect(result.unknown).toBeUndefined();
  expect(parseHash(buildHash("classification-results", result)).query).toEqual(source);
});

test("从证据跳转产品资料仍保护未保存的人工修正", async () => {
  vi.spyOn(api, "classificationResultVersions").mockResolvedValue([]);
  vi.spyOn(api, "resultTaxonomy").mockResolvedValue({ labels: [] });
  const corrected = vi.spyOn(api, "correctClassificationResult");
  const current = {
    ...record,
    classification: {
      semantic_units: [{ evidence: "synthetic", opinion: "原观点", label_code: "FIT" }],
    },
  };
  render(
    <EvidenceDrawer
      group={{ record: current, members: [], member_count: 1 }}
      analysisContext="user_feedback"
      onClose={vi.fn()}
      onSaved={vi.fn()}
      onViewProduct={() =>
        navigateHash(
          "data-assets",
          evidenceProductQuery(current, classificationResultRouteState(source)),
        )
      }
      returnFocusRef={{ current: null }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  await screen.findByLabelText("观点 1 用户观点");
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "保留的人工观点" },
  });
  fireEvent.click(screen.getByText("业务信息"));
  fireEvent.click(screen.getByRole("button", { name: "查看产品资料" }));
  expect(parseHash().page).toBe("classification-results");
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("观点 1 用户观点")).toHaveValue("保留的人工观点");
  fireEvent.click(screen.getByRole("button", { name: "查看产品资料" }));
  fireEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  await waitFor(() => expect(parseHash().page).toBe("data-assets"));
  expect(corrected).not.toHaveBeenCalled();
});

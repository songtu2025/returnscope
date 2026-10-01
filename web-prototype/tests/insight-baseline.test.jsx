import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ReturnReasonInsightBaseline } from "../src/features/analysis-dashboards/ReturnReasonInsightBaseline";

afterEach(cleanup);

const data = {
  total_record_count: 31375,
  counting_basis: "feedback_group",
  selected_reason: { value: "OTHER", label: "实物与预期不符", record_count: 1365 },
  subject_breakdown: [{ value: "PRODUCT", label: "商品相关" }],
  co_reasons: [
    {
      value: "MATERIAL",
      label: "材料廉价",
      record_count: 122,
      baseline_record_count: 303,
      lift: 9.25,
    },
  ],
  products: [
    { value: "产品 A", record_count: 588, total_record_count: 7173, lift: 1.88 },
  ],
};
const route = {
  listing: "L1",
  subject: "PRODUCT",
  dateFrom: "2026-01-01",
  dateTo: "2026-08-03",
};

test("基线说明展示服务端计数和当前范围，不从四舍五入倍数反推基线", () => {
  render(<ReturnReasonInsightBaseline data={data} route={route} loading={false} />);
  const companion = screen.getByRole("row", { name: /伴随原因：材料廉价/ });
  expect(within(companion).getByText("122 / 1,365 = 8.9%")).toBeVisible();
  expect(within(companion).getByText("303 / 31,375 = 1.0%")).toBeVisible();
  expect(within(companion).getByText("9.25×")).toBeVisible();
  const product = screen.getByRole("row", { name: /商品：产品 A/ });
  expect(within(product).getByText("588 / 7,173 = 8.2%")).toBeVisible();
  expect(within(product).getByText("1,365 / 31,375 = 4.4%")).toBeVisible();
  expect(screen.getByText(/2026-01-01 至 2026-08-03 · L1.*商品相关/)).toBeVisible();
});

test("筛选更新及失败时不展示旧计算明细", () => {
  const view = render(
    <ReturnReasonInsightBaseline data={data} route={route} loading />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("正在更新计算明细");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  view.rerender(
    <ReturnReasonInsightBaseline
      data={data}
      route={route}
      loading={false}
      error="失败"
    />,
  );
  expect(screen.getByRole("alert")).toBeVisible();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("缺少基线计数时保持未知，不伪造零值", () => {
  render(
    <ReturnReasonInsightBaseline
      data={{
        ...data,
        co_reasons: [{ ...data.co_reasons[0], baseline_record_count: undefined }],
      }}
      route={route}
      loading={false}
    />,
  );
  expect(screen.getByText("-- / 31,375")).toBeVisible();
});

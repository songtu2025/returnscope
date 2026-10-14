import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ManualSemanticFields } from "../src/features/classification-results/ManualSemanticFields";
import { semanticItemErrors } from "../src/features/classification-results/manualSemanticValidation";
afterEach(cleanup);
const labels = [{ code: "FIT", name: "尺码", allowed_sentiments: ["NEGATIVE"] }];
test("每个阻止保存的字段都有具体提示和程序关联", () => {
  const item = {
    item_id: "new",
    evidence_text: "",
    opinion: "",
    label_code: "",
    sentiment: "",
  };
  render(
    <ManualSemanticFields
      items={[item]}
      labels={labels}
      disabled={false}
      loading={false}
      onEdit={vi.fn()}
      onRemove={vi.fn()}
    />,
  );
  expect(screen.getByText("请填写支持观点的原文证据")).toBeVisible();
  expect(screen.getByText("请填写用户观点")).toBeVisible();
  expect(screen.getByText("请选择有效的归类标签")).toBeVisible();
  expect(screen.getByText("请确定评价方向")).toBeVisible();
  for (const name of ["观点 1 原文证据", "观点 1 用户观点"]) {
    const field = screen.getByLabelText(name);
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(
      document.getElementById(field.getAttribute("aria-describedby")),
    ).toHaveAttribute("role", "alert");
  }
});
test("单一评价方向沿用标签规则，多方向未选择时阻止保存", () => {
  const item = {
    item_id: "valid",
    evidence_text: "too small",
    opinion: "偏小",
    label_code: "FIT",
    sentiment: "",
  };
  expect(Object.values(semanticItemErrors(item, labels))).toEqual(["", "", "", ""]);
  expect(
    semanticItemErrors(item, [
      { ...labels[0], allowed_sentiments: ["POSITIVE", "NEGATIVE"] },
    ]).sentiment,
  ).toBe("请确定评价方向");
});

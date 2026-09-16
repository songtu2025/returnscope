import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ClassificationHierarchyEditor } from "../src/features/classification-standards/ClassificationHierarchyEditor";
import { ClassificationExcelImport } from "../src/features/classification-standards/ClassificationExcelImport";
import { ClassificationLabelWorkbench } from "../src/features/classification-standards/ClassificationLabelWorkbench";
import { taxonomyPath } from "../src/lib/taxonomyPresentation";

const api = vi.hoisted(() => ({ previewClassificationExcel: vi.fn() }));
vi.mock("../src/shared/api/classificationStandardApi", () => ({
  classificationStandardApi: api,
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const content = {
  structure_version: 2,
  categories: [
    { code: "FUNCTION", name: "功能", parent_code: null },
    { code: "WARMTH", name: "保暖性", parent_code: "FUNCTION" },
    { code: "QUALITY", name: "质量", parent_code: null },
  ],
  labels: [
    {
      code: "COLD",
      name: "不保暖",
      parent_code: "WARMTH",
      group: "功能",
      description: "保暖不足",
      allowed_sentiments: ["NEGATIVE"],
      keywords: [],
      allowed_claim_ids: [],
    },
  ],
  validation_rules: {},
};

test("分类改名和移动更新叶标签路径，禁止循环及删除带子节点的分类", async () => {
  const user = userEvent.setup();
  function Editor() {
    const [value, setValue] = useState(content);
    return (
      <>
        <ClassificationHierarchyEditor content={value} onChange={setValue} />
        <output>{taxonomyPath(value, value.labels[0]).join(" → ")}</output>
      </>
    );
  }
  render(<Editor />);
  await user.click(screen.getByText(/维护分类层级/));
  await user.selectOptions(screen.getByLabelText("选择分类节点"), "FUNCTION");
  expect(screen.getByRole("button", { name: "删除分类" })).toBeDisabled();
  expect(
    screen.getByLabelText("分类的上级").querySelector('option[value="WARMTH"]'),
  ).toBeNull();
  await user.selectOptions(screen.getByLabelText("选择分类节点"), "WARMTH");
  await user.selectOptions(screen.getByLabelText("分类的上级"), "QUALITY");
  expect(screen.getByRole("status")).toHaveTextContent("质量 → 保暖性 → 不保暖");
});

test("层级标签工作台保留树目录并允许选择标签的父分类", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(
    <ClassificationLabelWorkbench
      content={content}
      savedContent={content}
      onChange={onChange}
      editable
      initiallyEditing
      section="labels"
    />,
  );
  expect(screen.getByText("功能", { selector: "summary" })).toBeVisible();
  expect(screen.getByText("保暖性", { selector: "summary" })).toBeVisible();
  await user.selectOptions(screen.getByLabelText("标签的上级分类"), "QUALITY");
  expect(onChange.mock.lastCall[0].labels[0]).toMatchObject({
    parent_code: "QUALITY",
    group: "质量",
  });
});

test("Excel先选工作表再确认映射，未知方向可采用草稿且保留发布提示", async () => {
  const user = userEvent.setup();
  const onApply = vi.fn();
  const headers = ["一级标签", "二级标签", "三级标签-AI", "三级标签-处理", "标签类型"];
  api.previewClassificationExcel
    .mockResolvedValueOnce({
      sheets: ["Sheet2"],
      headers: [],
      content: null,
      issues: [],
    })
    .mockResolvedValueOnce({ sheets: ["Sheet2"], headers, content: null, issues: [] })
    .mockResolvedValueOnce({
      sheets: ["Sheet2"],
      headers,
      content,
      issues: [{ severity: "warning", row: 3, message: "评价方向待确认" }],
      validation: { blocking: ["至少选择一种评价方向"] },
    });
  render(
    <ClassificationExcelImport
      prepareDraft={async () => ({ id: "draft-1" })}
      onApply={onApply}
    />,
  );
  await user.upload(
    screen.getByLabelText("选择标签框架 Excel"),
    new File(["fixture"], "框架.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
  );
  await user.selectOptions(await screen.findByLabelText("标签框架工作表"), "Sheet2");
  await user.click(await screen.findByRole("button", { name: "生成预览" }));
  expect(
    await screen.findByText("功能 → 保暖性 → 不保暖", { selector: "p" }),
  ).toBeVisible();
  expect(screen.getByText("至少选择一种评价方向")).toBeVisible();
  expect(api.previewClassificationExcel.mock.lastCall[3].hierarchy_columns).toEqual([
    "一级标签",
    "二级标签",
    "三级标签-处理",
  ]);
  await user.click(screen.getByRole("button", { name: "采用预览并继续编辑" }));
  expect(onApply).toHaveBeenCalledWith(content, "框架.xlsx");
});

test("解析结构错误阻止采用预览", async () => {
  const user = userEvent.setup();
  api.previewClassificationExcel.mockResolvedValue({
    sheets: ["Sheet2"],
    headers: [],
    content,
    issues: [{ severity: "blocking", row: 2, message: "缺少中间层级" }],
  });
  render(
    <ClassificationExcelImport
      prepareDraft={async () => ({ id: "draft-1" })}
      onApply={vi.fn()}
    />,
  );
  await user.upload(
    screen.getByLabelText("选择标签框架 Excel"),
    new File(["fixture"], "框架.xlsx"),
  );
  expect(
    await screen.findByRole("button", { name: "采用预览并继续编辑" }),
  ).toBeDisabled();
});

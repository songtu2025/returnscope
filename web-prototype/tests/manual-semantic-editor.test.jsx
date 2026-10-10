import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ManualSemanticEditor } from "../src/features/classification-results/ManualSemanticEditor";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";

const mocks = vi.hoisted(() => ({
  resultTaxonomy: vi.fn(),
  correctClassificationResult: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
const group = {
  member_count: 2,
  members: [],
  record: {
    id: "record-1",
    result_version_id: "version-1",
    classification: {
      semantic_units: [
        {
          evidence: "too small",
          opinion: "偏小",
          label_code: "FIT",
          sentiment: "NEGATIVE",
        },
      ],
    },
  },
};
const props = {
  group,
  onSaved: vi.fn(),
  onCancel: vi.fn(),
  onDirtyChange: vi.fn(),
  onSavingChange: vi.fn(),
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.resultTaxonomy.mockResolvedValue({
    labels: [{ code: "FIT", name: "尺寸", allowed_sentiments: ["NEGATIVE"] }],
  });
  mocks.correctClassificationResult.mockResolvedValue({ version_id: "version-2" });
});
afterEach(cleanup);
test("直接保存语义不要求复核原因和批次，关联源明细由服务端确定", async () => {
  render(<ManualSemanticEditor {...props} />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "整体尺寸偏小" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  await waitFor(() => expect(props.onSaved).toHaveBeenCalledWith("version-2"));
  expect(mocks.correctClassificationResult).toHaveBeenCalledWith(
    "version-1",
    "record-1",
    {
      semantic_items: [
        {
          item_id: "unit:0",
          evidence_text: "too small",
          opinion: "整体尺寸偏小",
          label_code: "FIT",
          sentiment: "NEGATIVE",
        },
      ],
    },
  );
  expect(screen.queryByText("复核原因")).not.toBeInTheDocument();
});
test("保存冲突保留用户输入并恢复保存按钮", async () => {
  mocks.correctClassificationResult.mockRejectedValue(
    Object.assign(new Error("结果已更新，请刷新后重新修正"), { status: 409 }),
  );
  render(<ManualSemanticEditor {...props} />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "人工输入" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("结果已更新");
  expect(screen.getByLabelText("观点 1 用户观点")).toHaveValue("人工输入");
  expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled();
  expect(props.onSaved).not.toHaveBeenCalled();
});
test("删除所有错误观点可保存为人工已处理", async () => {
  render(<ManualSemanticEditor {...props} />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "删除观点 1" }));
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  await waitFor(() =>
    expect(mocks.correctClassificationResult).toHaveBeenCalledWith(
      "version-1",
      "record-1",
      { semantic_items: [] },
    ),
  );
});

test("证据抽屉关闭前保护未保存输入，继续编辑后内容仍在", async () => {
  const close = vi.fn();
  render(
    <EvidenceDrawer
      group={group}
      analysisContext="user_feedback"
      onSaved={vi.fn()}
      onClose={close}
      returnFocusRef={{ current: null }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  await waitFor(() => expect(screen.getByLabelText("观点 1 原文证据")).toHaveFocus());
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "保留的人工观点" },
  });
  fireEvent.click(screen.getByRole("button", { name: "关闭证据抽屉" }));
  expect(screen.getByRole("alert")).toHaveTextContent("有未保存的修改");
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("观点 1 用户观点")).toHaveValue("保留的人工观点");
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
  expect(close).toHaveBeenCalledOnce();
});

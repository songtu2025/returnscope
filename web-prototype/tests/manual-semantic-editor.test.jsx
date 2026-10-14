import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ManualSemanticEditor } from "../src/features/classification-results/ManualSemanticEditor";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";

const mocks = vi.hoisted(() => ({
  resultTaxonomy: vi.fn(),
  correctClassificationResult: vi.fn(),
  classificationResultVersions: vi.fn(),
  classificationResultRecordGroups: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: mocks }));
const group = {
  member_count: 2,
  members: [],
  record: {
    id: "record-1",
    source_record_id: "source-1",
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
  expect(screen.getByRole("button", { name: "保存修正" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "加载最新结果并保留输入" })).toBeEnabled();
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

test("并发冲突加载同一反馈组的最新结果，保留草稿并由用户再次保存", async () => {
  mocks.correctClassificationResult.mockRejectedValueOnce(
    Object.assign(new Error("结果已更新"), { status: 409 }),
  );
  mocks.classificationResultVersions.mockResolvedValue([{ version_id: "version-2" }]);
  mocks.classificationResultRecordGroups.mockResolvedValue({
    items: [
      {
        ...group,
        record: { ...group.record, id: "record-2", result_version_id: "version-2" },
      },
    ],
  });
  render(<ManualSemanticEditor {...props} />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "保留草稿" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "加载最新结果并保留输入" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("已保留你的输入");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  expect(screen.getByLabelText("观点 1 用户观点")).toHaveValue("保留草稿");
  expect(mocks.classificationResultRecordGroups).toHaveBeenCalledWith("version-2", {
    feedback_source_record_id: "source-1",
  });
  expect(mocks.correctClassificationResult).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  await waitFor(() =>
    expect(mocks.correctClassificationResult).toHaveBeenLastCalledWith(
      "version-2",
      "record-2",
      expect.objectContaining({
        semantic_items: [expect.objectContaining({ opinion: "保留草稿" })],
      }),
    ),
  );
});

test("保存并查看下一条只在保存成功后调用，保存中阻止切换和关闭", async () => {
  let finish;
  mocks.correctClassificationResult.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const move = vi.fn();
  const close = vi.fn();
  const saved = vi.fn();
  render(
    <EvidenceDrawer
      group={group}
      analysisContext="user_feedback"
      onClose={close}
      onSaved={saved}
      returnFocusRef={{ current: null }}
      navigation={{
        position: 0,
        total: 2,
        busy: false,
        locked: false,
        error: "",
        move,
        retry: vi.fn(),
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  const next = await screen.findByRole("button", { name: "保存并查看下一条" });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
  expect(screen.getByRole("button", { name: "下一条", exact: true })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "关闭证据抽屉" }));
  expect(close).not.toHaveBeenCalled();
  expect(move).not.toHaveBeenCalled();
  await finish({ version_id: "version-2" });
  await waitFor(() => expect(saved).toHaveBeenCalledWith("version-2", true));
});

test("未保存时切换反馈先确认，继续编辑保留输入", async () => {
  const move = vi.fn();
  render(
    <EvidenceDrawer
      group={group}
      analysisContext="user_feedback"
      onClose={vi.fn()}
      onSaved={vi.fn()}
      returnFocusRef={{ current: null }}
      navigation={{
        position: 0,
        total: 2,
        busy: false,
        locked: false,
        error: "",
        move,
        retry: vi.fn(),
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  await screen.findByLabelText("观点 1 用户观点");
  fireEvent.change(screen.getByLabelText("观点 1 用户观点"), {
    target: { value: "未保存观点" },
  });
  fireEvent.click(screen.getByRole("button", { name: "下一条", exact: true }));
  expect(move).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("观点 1 用户观点")).toHaveValue("未保存观点");
  fireEvent.click(screen.getByRole("button", { name: "下一条", exact: true }));
  fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
  expect(move).toHaveBeenCalledWith(1);
});

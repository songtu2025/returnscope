import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { HistoryRestoreButton } from "../src/components/HistoryRestoreButton";
import { TaskDraftActions } from "../src/features/task-create/TaskDraftActions";
import { SemanticHistory } from "../src/features/classification-results/SemanticHistory";
import {
  semanticChanges,
  restoreSemanticChange,
} from "../src/shared/api/historyRestore";

vi.mock("../src/shared/api/historyRestore", () => ({
  semanticChanges: vi.fn(),
  restoreSemanticChange: vi.fn(),
}));

afterEach(cleanup);

test("放弃创建必须确认，返回继续创建不丢失草稿", async () => {
  const user = userEvent.setup();
  const discard = vi.fn();
  render(<TaskDraftActions disabled={false} onDiscard={discard} />);
  await user.click(screen.getByText("放弃本次创建"));
  await user.click(screen.getByText("继续创建"));
  expect(discard).not.toHaveBeenCalled();
  await user.click(screen.getByText("放弃本次创建"));
  await user.click(screen.getByText("确认放弃"));
  expect(discard).toHaveBeenCalledTimes(1);
});

test("历史还原冲突保留确认与错误，重新核对后可以重试", async () => {
  const user = userEvent.setup();
  const restore = vi
    .fn()
    .mockRejectedValueOnce(new Error("数据已更新，请刷新"))
    .mockResolvedValueOnce(undefined);
  render(<HistoryRestoreButton onRestore={restore} />);
  await user.click(screen.getByText("还原此次修改"));
  await user.click(screen.getByText("确认还原"));
  expect(await screen.findByRole("alert")).toHaveTextContent("数据已更新");
  await user.click(screen.getByText("确认还原"));
  expect(await screen.findByText("还原此次修改")).toBeEnabled();
  expect(restore).toHaveBeenCalledTimes(2);
});

test("在途创建不允许放弃，避免创建成功后丢失去向", () => {
  render(<TaskDraftActions disabled onDiscard={vi.fn()} />);
  expect(screen.getByText("放弃本次创建")).toBeDisabled();
});

test("语义历史还原指定反馈组并切换到保存后的结果", async () => {
  const user = userEvent.setup();
  vi.mocked(semanticChanges).mockResolvedValue([
    {
      id: "edit-1",
      actor_name: "验收用户",
      created_at: "2026-10-14T00:00:00Z",
      before: { semantic_units: [{ label_code: "FIT", opinion: "原观点" }] },
      after: {},
    },
  ]);
  vi.mocked(restoreSemanticChange).mockResolvedValue({ version_id: "current-result" });
  const saved = vi.fn();
  const busy = vi.fn();
  render(
    <SemanticHistory
      versionId="result-1"
      recordId="record-1"
      onSaved={saved}
      onBusyChange={busy}
    />,
  );
  await user.click(screen.getByText("查看修正历史"));
  expect(await screen.findByText(/原观点/)).toBeInTheDocument();
  await user.click(screen.getByText("还原此次修改"));
  await user.click(screen.getByText("确认还原"));
  expect(restoreSemanticChange).toHaveBeenCalledWith("result-1", "record-1", "edit-1");
  expect(saved).toHaveBeenCalledWith("current-result");
  expect(busy.mock.calls).toEqual([[true], [false]]);
});

test.each([
  ["空列表", [], "暂无人工修正记录"],
  [
    "历史记录",
    [
      {
        id: "retry-edit",
        actor_name: "合成用户",
        created_at: "2026-10-16T00:00:00Z",
        before: { semantic_units: [{ label_code: "FIT", opinion: "重试读取的观点" }] },
      },
    ],
    /重试读取的观点/,
  ],
])("语义历史首次失败后重试返回%s，清除旧错误", async (_label, entries, expected) => {
  const user = userEvent.setup();
  vi.mocked(semanticChanges)
    .mockRejectedValueOnce(new Error("首次历史读取失败"))
    .mockResolvedValueOnce(entries);
  render(
    <SemanticHistory
      versionId="result-1"
      recordId="record-1"
      onSaved={vi.fn()}
      onBusyChange={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "查看修正历史" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("首次历史读取失败");
  await user.click(screen.getByRole("button", { name: "查看修正历史" }));
  expect(await screen.findByText(expected)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "收起修正历史" })).toBeEnabled();
});

test("语义历史连续读取失败显示最新错误并仍可重试", async () => {
  const user = userEvent.setup();
  vi.mocked(semanticChanges)
    .mockRejectedValueOnce(new Error("首次历史读取失败"))
    .mockRejectedValueOnce(new Error("第二次历史读取失败"))
    .mockResolvedValueOnce([]);
  render(
    <SemanticHistory
      versionId="result-1"
      recordId="record-1"
      onSaved={vi.fn()}
      onBusyChange={vi.fn()}
    />,
  );
  await user.click(screen.getByRole("button", { name: "查看修正历史" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("首次历史读取失败");
  await user.click(screen.getByRole("button", { name: "查看修正历史" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("第二次历史读取失败");
  expect(screen.queryByText("首次历史读取失败")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看修正历史" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "查看修正历史" }));
  expect(await screen.findByText("暂无人工修正记录")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

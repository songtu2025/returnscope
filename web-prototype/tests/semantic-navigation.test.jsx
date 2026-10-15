import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";
import { requestNavigation } from "../src/app/navigationGuard";
import { ClassificationResultDetailView } from "../src/features/classification-results/ClassificationResultDetailView";
const refresh = vi.hoisted(() => vi.fn());
vi.mock("../src/shared/serverState", () => ({ refreshServerState: refresh }));
vi.mock("../src/features/classification-results/resultDetailPresentation", () => ({
  resultDetailPresentation: () => ({}),
}));
vi.mock("../src/features/classification-results/resultDetailActions", () => ({
  resultDetailActions: () => ({}),
}));
vi.mock("../src/features/classification-results/ResultDetailHeader", () => ({
  ResultDetailHeader: () => null,
}));
vi.mock("../src/features/classification-results/ResultDetailMetrics", () => ({
  ResultDetailMetrics: () => null,
}));
vi.mock("../src/features/classification-results/ResultDetailDrilldown", () => ({
  ResultDetailDrilldown: () => null,
}));
vi.mock("../src/features/classification-results/ResultDetailRecords", () => ({
  ResultDetailRecords: () => null,
}));
const api = vi.hoisted(() => ({
  resultTaxonomy: vi.fn(),
  correctClassificationResult: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
const group = {
  members: [],
  member_count: 1,
  record: {
    id: "record",
    result_version_id: "version",
    classification: {
      semantic_units: [
        {
          evidence: "small",
          opinion: "偏小",
          label_code: "FIT",
          sentiment: "NEGATIVE",
        },
      ],
    },
  },
};
beforeEach(() => {
  vi.resetAllMocks();
  refresh.mockResolvedValue(undefined);
  api.resultTaxonomy.mockResolvedValue({
    labels: [{ code: "FIT", name: "尺寸", allowed_sentiments: ["NEGATIVE"] }],
  });
  api.correctClassificationResult.mockResolvedValue({ version_id: "next" });
});
afterEach(cleanup);

test("普通语义保存中请求离开，提交后优先原用户目标而非内部版本导航", async () => {
  let finish;
  api.correctClassificationResult.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const saved = vi.fn();
  const refreshRelated = vi.fn().mockResolvedValue(undefined);
  render(
    <EvidenceDrawer
      group={group}
      onSaved={saved}
      onSavedBeforeExit={refreshRelated}
      onClose={vi.fn()}
      returnFocusRef={{ current: null }}
      analysisContext="user_feedback"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  const opinion = await screen.findByLabelText("观点 1 用户观点");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.change(opinion, { target: { value: "待提交观点" } });
  fireEvent.click(screen.getByRole("button", { name: "保存修正" }));
  const proceed = vi.fn();
  act(() => expect(requestNavigation(proceed)).toBe(false));
  expect(proceed).not.toHaveBeenCalled();
  await act(async () => finish({ version_id: "next" }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(api.correctClassificationResult).toHaveBeenCalledOnce();
  expect(refreshRelated).toHaveBeenCalledOnce();
  expect(saved).not.toHaveBeenCalled();
});

test.each([false, true])(
  "退出保存刷新关联缓存一次，刷新失败=%s也不二次写入或跳转版本",
  async (failure) => {
    if (failure) refresh.mockRejectedValueOnce(new Error("刷新失败"));
    const notify = vi.fn();
    const saved = vi.fn();
    render(
      <ClassificationResultDetailView
        route={{ tab: "records" }}
        result={{ analysis_context: "user_feedback" }}
        selectedGroup={group}
        policy={{}}
        evidenceNavigation={{ saved }}
        evidenceTriggerRef={{ current: null }}
        notify={notify}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
    const opinion = await screen.findByLabelText("观点 1 用户观点");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
    );
    fireEvent.change(opinion, { target: { value: "退出前修正" } });
    const proceed = vi.fn();
    act(() => requestNavigation(proceed));
    fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
    await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
    expect(api.correctClassificationResult).toHaveBeenCalledOnce();
    expect(saved).not.toHaveBeenCalled();
    expect(refresh).toHaveBeenCalledExactlyOnceWith(expect.any(Function), [
      "classification-results",
      "analysis-dashboards",
      "analysis-tasks",
      "workbench",
    ]);
    if (failure)
      expect(notify).toHaveBeenCalledWith(
        "人工修正已保存，部分关联数据更新失败，可重试",
        "error",
      );
  },
);
async function edit() {
  const saved = vi.fn();
  const close = vi.fn();
  render(
    <EvidenceDrawer
      group={group}
      onSaved={saved}
      onClose={close}
      returnFocusRef={{ current: null }}
      analysisContext="user_feedback"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "人工修正" }));
  const opinion = await screen.findByLabelText("观点 1 用户观点");
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存修正" })).toBeEnabled(),
  );
  fireEvent.change(opinion, { target: { value: "人工观点" } });
  return { saved, close, opinion };
}
test("语义改回原值不拦导航；路由确认Esc不再触发抽屉关闭确认", async () => {
  const { opinion, close } = await edit();
  act(() => expect(requestNavigation(vi.fn())).toBe(false));
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByText("离开前是否保存本次修改？")).not.toBeInTheDocument();
  expect(screen.queryByText(/有未保存的修改/)).not.toBeInTheDocument();
  expect(opinion).toHaveValue("人工观点");
  expect(close).not.toHaveBeenCalled();
  fireEvent.change(opinion, { target: { value: "偏小" } });
  expect(requestNavigation(vi.fn())).toBe(true);
});
test("语义退出保存失败保留输入，重试成功执行目标且不走结果版本导航", async () => {
  api.correctClassificationResult.mockRejectedValueOnce(new Error("保存失败"));
  const { saved, opinion } = await edit();
  const proceed = vi.fn();
  act(() => requestNavigation(proceed));
  expect(screen.getByRole("button", { name: "保存修正" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  expect(await screen.findByText("保存失败")).toBeVisible();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toBeEnabled(),
  );
  expect(opinion).toHaveValue("人工观点");
  expect(proceed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() => expect(proceed).toHaveBeenCalledOnce());
  expect(saved).not.toHaveBeenCalled();
  expect(api.correctClassificationResult).toHaveBeenCalledTimes(2);
});

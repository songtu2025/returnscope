import { beforeEach, expect, test, vi } from "vitest";
import { taskExecutionActions } from "../src/features/task-runtime/taskExecutionActions";

const mocks = vi.hoisted(() => ({
  retryTaskSegment: vi.fn(),
  retrySegmentResultPublish: vi.fn(),
  refresh: vi.fn(),
  controlTaskSegment: vi.fn(),
}));
vi.mock("../src/features/task-runtime/taskMonitorRequests", () => ({
  taskMonitorApi: mocks,
  errorMessage: (error) => error.message,
  errorStatus: (error) => error.status,
}));
vi.mock("../src/shared/serverState", () => ({ refreshServerState: mocks.refresh }));

beforeEach(() => vi.resetAllMocks());

function context() {
  return {
    selected: { id: "synthetic-task", revision: 3 },
    notify: vi.fn(),
    setSelected: vi.fn(),
    setActionError: vi.fn(),
    loadTasks: vi.fn().mockResolvedValue(undefined),
    loadSelected: vi.fn(),
    mutateCache: vi.fn(),
  };
}

test("失败项重新排队后刷新首页待办", async () => {
  const state = context();
  const updated = { status: "queued", revision: 4 };
  mocks.retryTaskSegment.mockResolvedValue(updated);
  mocks.refresh.mockResolvedValue(undefined);
  const result = await taskExecutionActions(state).onRetrySegment("listing-1", {
    expected_revision: 3,
  });
  expect(result).toBe(true);
  expect(state.setSelected).toHaveBeenCalledWith(updated);
  expect(mocks.refresh).toHaveBeenCalledWith(state.mutateCache, ["workbench"]);
});

test("结果发布重试成功后刷新结果、看板和首页", async () => {
  const state = context();
  mocks.retrySegmentResultPublish.mockResolvedValue({ status: "completed" });
  mocks.refresh.mockResolvedValue(undefined);
  expect(await taskExecutionActions(state).onRetryResultPublish("listing-1")).toBe(
    true,
  );
  expect(mocks.refresh).toHaveBeenCalledWith(state.mutateCache, [
    "classification-results",
    "analysis-dashboards",
    "workbench",
  ]);
  expect(state.notify).toHaveBeenCalledWith("分类结果已重新生成");
  expect(mocks.retryTaskSegment).not.toHaveBeenCalled();
});

test("结果已生成但刷新失败时仍保留成功结果", async () => {
  const state = context();
  const updated = { status: "completed" };
  mocks.retrySegmentResultPublish.mockResolvedValue(updated);
  mocks.refresh.mockRejectedValue(new Error("合成刷新失败"));
  expect(await taskExecutionActions(state).onRetryResultPublish("listing-1")).toBe(
    true,
  );
  expect(state.setSelected).toHaveBeenCalledExactlyOnceWith(updated);
  expect(state.notify).toHaveBeenCalledWith(
    "结果已重新生成，任务列表或关联数据刷新失败，请刷新后查看",
    "error",
  );
  expect(mocks.retrySegmentResultPublish).toHaveBeenCalledTimes(1);
});

test("重试被并发版本校验拒绝时刷新详情，保留待办", async () => {
  const state = context();
  mocks.retrySegmentResultPublish.mockRejectedValue(
    Object.assign(new Error("版本冲突"), { status: 409 }),
  );
  expect(await taskExecutionActions(state).onRetryResultPublish("listing-1")).toBe(
    false,
  );
  expect(state.loadSelected).toHaveBeenCalledOnce();
  expect(state.setSelected).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
});

test.each(["loadTasks", "related", "both"])(
  "Listing已提交但%s刷新失败仍返回成功并保留服务器结果",
  async (failure) => {
    const state = context();
    const updated = { revision: 4, segments: [] };
    mocks.controlTaskSegment.mockResolvedValue(updated);
    mocks.refresh.mockResolvedValue(undefined);
    if (failure !== "related")
      state.loadTasks.mockRejectedValueOnce(new Error("列表刷新失败"));
    if (failure !== "loadTasks")
      mocks.refresh.mockRejectedValueOnce(new Error("关联刷新失败"));
    expect(await taskExecutionActions(state).onSegmentAction("segment", "delete")).toBe(
      true,
    );
    expect(state.setSelected).toHaveBeenCalledExactlyOnceWith(updated);
    expect(state.notify).toHaveBeenCalledWith("Listing 移除请求已提交，结果和看板保留");
    expect(state.notify).toHaveBeenCalledWith(
      "Listing 操作已提交，任务列表或关联数据刷新失败，请刷新后查看",
      "error",
    );
    expect(mocks.controlTaskSegment).toHaveBeenCalledExactlyOnceWith(
      "synthetic-task",
      "segment",
      "delete",
      { expected_revision: 3, note: "" },
    );
    expect(state.loadTasks).toHaveBeenCalledOnce();
    expect(mocks.refresh).toHaveBeenCalledWith(state.mutateCache, [
      "workbench",
      "data-assets",
      "task-recycle",
    ]);
  },
);

test.each(["retry", "publish"])(
  "%s写成功但列表刷新失败不误报提交失败",
  async (action) => {
    const state = context();
    state.loadTasks.mockRejectedValue(new Error("列表刷新失败"));
    mocks.refresh.mockResolvedValue(undefined);
    mocks.retryTaskSegment.mockResolvedValue({ revision: 4 });
    mocks.retrySegmentResultPublish.mockResolvedValue({ revision: 4 });
    const actions = taskExecutionActions(state);
    expect(
      await (action === "retry"
        ? actions.onRetrySegment("segment", { expected_revision: 3 })
        : actions.onRetryResultPublish("segment")),
    ).toBe(true);
    expect(state.setSelected).toHaveBeenCalledOnce();
    expect(mocks.refresh).toHaveBeenCalledOnce();
    expect(state.notify).toHaveBeenCalledWith(
      expect.stringContaining("刷新失败"),
      "error",
    );
  },
);

test("Listing写失败返回false不刷关联，409详情读取失败仍保留原错误", async () => {
  const state = context();
  mocks.controlTaskSegment
    .mockRejectedValueOnce(new Error("提交失败"))
    .mockRejectedValueOnce(Object.assign(new Error("版本冲突"), { status: 409 }));
  const actions = taskExecutionActions(state);
  expect(await actions.onSegmentAction("segment", "pause")).toBe(false);
  expect(state.loadSelected).not.toHaveBeenCalled();
  state.loadSelected.mockRejectedValue(new Error("读取失败"));
  expect(await actions.onSegmentAction("segment", "pause")).toBe(false);
  expect(state.notify).toHaveBeenCalledWith("版本冲突", "error");
  expect(state.notify).toHaveBeenCalledWith(
    "任务资料刷新失败，操作未提交，请刷新后重试",
    "error",
  );
  expect(state.setSelected).not.toHaveBeenCalled();
  expect(state.loadTasks).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
});

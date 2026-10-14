import { beforeEach, expect, test, vi } from "vitest";
import { taskExecutionActions } from "../src/features/task-runtime/taskExecutionActions";

const mocks = vi.hoisted(() => ({
  retryTaskSegment: vi.fn(),
  retrySegmentResultPublish: vi.fn(),
  refresh: vi.fn(),
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
    "结果已重新生成，关联数据刷新失败，可重试",
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

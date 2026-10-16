import { beforeEach, expect, test, vi } from "vitest";
import { taskExecutionActions } from "../src/features/task-runtime/taskExecutionActions";
import { segmentActionAvailable } from "../src/features/task-runtime/segmentBoardRowPolicy";

const api = vi.hoisted(() => ({ controlTaskSegment: vi.fn(), refresh: vi.fn() }));
vi.mock("../src/api", () => ({ api }));
vi.mock("../src/shared/serverState", () => ({ refreshServerState: api.refresh }));
const segment = (key, status = "paused", extra = {}) => ({
  id: key,
  segment_key: key,
  agent_key: "synthetic",
  status,
  ...extra,
});
const task = (revision = 3, segments = [segment("a"), segment("b"), segment("c")]) => ({
  id: "synthetic-task",
  revision,
  segments,
});
function context(selected = task()) {
  return {
    selected,
    setSelected: vi.fn(),
    setActionError: vi.fn(),
    notify: vi.fn(),
    loadSelected: vi.fn().mockResolvedValue(selected),
    loadTasks: vi.fn().mockResolvedValue(true),
    mutateCache: vi.fn(),
  };
}
beforeEach(() => vi.resetAllMocks());

test("逐项串行提交，后项使用前项返回的修订号，重复key仅提交一次", async () => {
  const state = context();
  let release;
  api.controlTaskSegment
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    )
    .mockResolvedValueOnce(task(5));
  const pending = taskExecutionActions(state).onBatchSegmentAction(
    ["a", "a", "b"],
    "resume",
  );
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(1);
  release(task(4));
  const result = await pending;
  expect(
    api.controlTaskSegment.mock.calls.map((call) => call[3].expected_revision),
  ).toEqual([3, 4]);
  expect(result.succeeded).toEqual(["a", "b"]);
  expect(state.setSelected).toHaveBeenLastCalledWith(task(5));
  expect(state.loadTasks).toHaveBeenCalledTimes(1);
});

test.each([409, 0, 503])(
  "第2项失败%s后停止，保留已成功和未执行项并读取核对",
  async (status) => {
    const state = context();
    api.controlTaskSegment
      .mockResolvedValueOnce(task(4))
      .mockRejectedValueOnce(Object.assign(new Error("合成错误"), { status }));
    const result = await taskExecutionActions(state).onBatchSegmentAction(
      ["a", "b", "c"],
      "resume",
    );
    expect(api.controlTaskSegment).toHaveBeenCalledTimes(2);
    expect(result).toMatchObject({
      succeeded: ["a"],
      pending: ["c"],
      failed: { key: "b", uncertain: status !== 409 },
      refreshRequired: false,
    });
    expect(state.loadSelected).toHaveBeenCalledTimes(1);
  },
);

test("结果未知且读取失败要求先刷新，独立重读不会重发POST", async () => {
  const state = context();
  api.controlTaskSegment.mockRejectedValueOnce(new TypeError("合成网络中断"));
  state.loadSelected.mockRejectedValueOnce(new Error("合成读取失败"));
  const actions = taskExecutionActions(state);
  const result = await actions.onBatchSegmentAction(["a", "b"], "resume");
  expect(result).toMatchObject({
    refreshRequired: true,
    failed: { uncertain: true },
    pending: ["b"],
  });
  state.loadSelected.mockResolvedValueOnce(task(4));
  expect(await actions.onRefreshSegments()).toBe(true);
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(1);
});

test("读取刷新失败不改写成功结果，跳过不符合操作资格的项", async () => {
  const state = context(task(3, [segment("a"), segment("b", "completed")]));
  api.controlTaskSegment.mockResolvedValueOnce(task(4, state.selected.segments));
  state.loadTasks.mockResolvedValueOnce(false);
  const result = await taskExecutionActions(state).onBatchSegmentAction(
    ["a", "b"],
    "resume",
  );
  expect(result).toMatchObject({ succeeded: ["a"], skipped: ["b"], failed: null });
  expect(api.controlTaskSegment).toHaveBeenCalledTimes(1);
  expect(state.notify).toHaveBeenCalledWith(
    expect.stringContaining("操作结果已保留"),
    "error",
  );
});

test.each([
  ["running", "pause", true],
  ["queued", "pause", true],
  ["retry_pending", "pause", true],
  ["paused", "pause", false],
  ["completed", "pause", false],
  ["paused", "resume", true],
  ["cancelled", "resume", true],
  ["completed", "resume", false],
  ["failed", "resume", false],
  ["completed", "delete", true],
  ["running", "delete", true],
  ["blocked", "delete", false],
])("复用单项操作资格：%s/%s=%s", (status, action, expected) => {
  expect(segmentActionAvailable(segment("a", status), action)).toBe(expected);
});
test.each([
  { deleted_at: "today" },
  { removal_requested_at: "today" },
  { requested_action: "pause" },
  { agent_key: "unknown" },
])("处理中或排除项不接受重复批量请求：%j", (extra) => {
  expect(segmentActionAvailable(segment("a", "running", extra), "delete")).toBe(false);
});
test("结果已删除的项不能继续执行，但仍允许移除任务引用", () => {
  const item = segment("a", "paused", { result_deleted_at: "today" });
  expect(segmentActionAvailable(item, "resume")).toBe(false);
  expect(segmentActionAvailable(item, "delete")).toBe(true);
});

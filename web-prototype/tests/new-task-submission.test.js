import { beforeEach, expect, test, vi } from "vitest";
const { apiMock } = vi.hoisted(() => ({
  apiMock: { createTask: vi.fn(), tasks: vi.fn() },
}));
vi.mock("../src/api", () => ({ api: apiMock }));
import { submitNewTask } from "../src/features/task-create/newTaskSubmission";

beforeEach(() => {
  vi.resetAllMocks();
  apiMock.createTask.mockResolvedValue({ id: "synthetic-task" });
  apiMock.tasks.mockResolvedValue([{ id: "synthetic-task" }]);
});

function submission(changes = {}) {
  return {
    submitting: false,
    preflight: { status: "ready", data: { plan_hash: "synthetic-plan" }, error: "" },
    unresolvedPolicy: "block_all",
    planState: {
      categoryCompletionRequired: false,
      countMismatch: false,
      noExecutable: false,
      requiresScopeConfirmation: false,
    },
    scopeConfirmed: false,
    form: {
      title: "  合成任务  ",
      dataset_version_id: "synthetic-data",
      product_version_id: "synthetic-products",
      config_version_id: "synthetic-config",
      store: "合成店铺",
      listing: "合成Listing",
      model_policy: { primary_model: "synthetic-model" },
    },
    segmentOrder: ["synthetic-b", "synthetic-a"],
    mutateServerState: vi.fn(async (key, data) =>
      data === undefined ? undefined : await data,
    ),
    setSubmitting: vi.fn(),
    setSubmitError: vi.fn(),
    setPrepared: vi.fn(),
    setPreflight: vi.fn(),
    setUnresolvedPolicy: vi.fn(),
    notify: vi.fn(),
    onDraftComplete: vi.fn(),
    onChanged: vi.fn(),
    onNavigate: vi.fn(),
    ...changes,
  };
}

test.each([
  { submitting: true },
  { preflight: { status: "idle", data: null } },
  { preflight: { status: "error", data: null } },
  { preflight: { status: "ready", data: null } },
  { unresolvedPolicy: "" },
  { planState: { categoryCompletionRequired: true } },
  { planState: { countMismatch: true } },
  { planState: { noExecutable: true } },
  { planState: { requiresScopeConfirmation: true }, scopeConfirmed: false },
])("启动校验未满足时不创建、刷新或修改状态：%s", async (changes) => {
  const props = submission(changes);
  await submitNewTask(props);
  expect(apiMock.createTask).not.toHaveBeenCalled();
  expect(apiMock.tasks).not.toHaveBeenCalled();
  expect(props.mutateServerState).not.toHaveBeenCalled();
  expect(props.setSubmitting).not.toHaveBeenCalled();
  expect(props.setSubmitError).not.toHaveBeenCalled();
  expect(props.notify).not.toHaveBeenCalled();
});

test("创建参数、任务列表缓存与成功回调保持顺序，保留表单原值", async () => {
  const order = [];
  const props = submission();
  const before = JSON.stringify(props.form);
  apiMock.createTask.mockImplementation(async () => {
    order.push("create");
    return { id: "synthetic-task" };
  });
  apiMock.tasks.mockImplementation(() => {
    order.push("tasks");
    return Promise.resolve([]);
  });
  props.mutateServerState.mockImplementation(async (key, data) => {
    order.push("cache");
    await data;
  });
  props.setSubmitting.mockImplementation((value) => order.push(`busy:${value}`));
  props.setSubmitError.mockImplementation((value) => order.push(`error:${value}`));
  props.notify.mockImplementation(() => order.push("notify"));
  props.onDraftComplete.mockImplementation(() => order.push("draft"));
  props.onChanged.mockImplementation(() => order.push("changed"));
  props.onNavigate.mockImplementation(() => order.push("navigate"));
  await submitNewTask(props);
  expect(apiMock.createTask).toHaveBeenCalledExactlyOnceWith({
    ...props.form,
    title: "合成任务",
    store: null,
    listing: null,
    plan_hash: "synthetic-plan",
    unresolved_policy: "block_all",
    segment_order: props.segmentOrder,
  });
  expect(props.mutateServerState).toHaveBeenCalledExactlyOnceWith(expect.any(Function));
  const predicate = props.mutateServerState.mock.calls[0][0];
  expect(predicate(["analysis-tasks", "list"])).toBe(true);
  expect(predicate(["workbench", "summary"])).toBe(true);
  expect(predicate(["data-assets", "products"])).toBe(false);
  expect(order).toEqual([
    "busy:true",
    "error:",
    "create",
    "cache",
    "notify",
    "draft",
    "changed",
    "navigate",
    "busy:false",
  ]);
  expect(JSON.stringify(props.form)).toBe(before);
});

test("关联刷新失败保留缓存并继续已创建任务的成功路径", async () => {
  const props = submission({ onDraftComplete: undefined });
  props.mutateServerState.mockRejectedValue(new Error("合成列表错误"));
  await submitNewTask(props);
  expect(props.mutateServerState).toHaveBeenCalledExactlyOnceWith(expect.any(Function));
  expect(props.notify).toHaveBeenCalledWith(
    "任务已创建，关联数据更新失败，可返回任务页重试",
    "error",
  );
  expect(props.onNavigate).toHaveBeenCalledExactlyOnceWith("tasks", {
    kind: "task",
    id: "synthetic-task",
  });
  expect(props.setSubmitError).toHaveBeenCalledExactlyOnceWith("");
});

test("刷新缓存失败不会误报创建失败或保留可重复提交的草稿", async () => {
  const props = submission();
  props.mutateServerState.mockRejectedValue(new Error("合成缓存错误"));
  await submitNewTask(props);
  expect(apiMock.createTask).toHaveBeenCalledOnce();
  expect(props.setSubmitError).toHaveBeenCalledExactlyOnceWith("");
  expect(props.onDraftComplete).toHaveBeenCalledOnce();
  expect(props.onNavigate).toHaveBeenCalledExactlyOnceWith("tasks", {
    kind: "task",
    id: "synthetic-task",
  });
  expect(props.setSubmitting).toHaveBeenLastCalledWith(false);
});

test("409 只使执行计划失效并清空处理策略，保持准备状态供重新预检", async () => {
  apiMock.createTask.mockRejectedValue(
    Object.assign(new Error("合成过期计划"), { status: 409 }),
  );
  const props = submission();
  await submitNewTask(props);
  expect(props.setPrepared).toHaveBeenCalledExactlyOnceWith(true);
  expect(props.setPreflight).toHaveBeenCalledExactlyOnceWith({
    status: "error",
    data: null,
    error: "执行计划已变化，请重新预检后再启动任务。",
  });
  expect(props.setUnresolvedPolicy).toHaveBeenCalledExactlyOnceWith("");
  expect(props.setSubmitError).toHaveBeenCalledExactlyOnceWith("");
  expect(props.notify).toHaveBeenCalledExactlyOnceWith("合成过期计划", "error");
  expect(apiMock.tasks).not.toHaveBeenCalled();
  expect(props.onChanged).not.toHaveBeenCalled();
});

test.each([new Error("合成创建失败"), "合成未知错误"])(
  "普通错误不清空计划或草稿，重试沿用原提交参数：%s",
  async (error) => {
    apiMock.createTask.mockRejectedValueOnce(error);
    const props = submission();
    await submitNewTask(props);
    expect(props.setSubmitError).toHaveBeenLastCalledWith(
      error instanceof Error ? error.message : "暂时无法创建任务，请重试。",
    );
    expect(props.setPrepared).not.toHaveBeenCalled();
    expect(props.setPreflight).not.toHaveBeenCalled();
    expect(props.onDraftComplete).not.toHaveBeenCalled();
    await submitNewTask(props);
    expect(apiMock.createTask).toHaveBeenCalledTimes(2);
    expect(apiMock.createTask.mock.calls[0]).toEqual(apiMock.createTask.mock.calls[1]);
    expect(props.onNavigate).toHaveBeenCalledExactlyOnceWith("tasks", {
      kind: "task",
      id: "synthetic-task",
    });
  },
);

test("成功回调异常仍走原错误反馈，onChanged 的返回 Promise 不阻塞跳转", async () => {
  const props = submission();
  props.onDraftComplete.mockImplementationOnce(() => {
    throw new Error("合成草稿回调失败");
  });
  await submitNewTask(props);
  expect(props.notify.mock.calls).toEqual([
    ["任务已创建，后台执行器会自动领取"],
    ["合成草稿回调失败", "error"],
  ]);
  expect(props.onNavigate).not.toHaveBeenCalled();
  props.onChanged.mockReturnValue(new Promise(() => {}));
  await submitNewTask(props);
  expect(props.onNavigate).toHaveBeenCalledExactlyOnceWith("tasks", {
    kind: "task",
    id: "synthetic-task",
  });
});

import { act, cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

const { apiProbe, newTaskPageProbe } = vi.hoisted(() => ({
  apiProbe: { task: vi.fn() },
  newTaskPageProbe: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: apiProbe }));
vi.mock("../src/features/task-create/NewTaskPage", () => ({
  NewTaskPage: (props) => {
    newTaskPageProbe(props);
    return <div>任务创建内容</div>;
  },
}));
import { PageLoadingScope } from "../src/app/PageLoadingScope";
import { TaskCreatePage } from "../src/features/task-create/TaskCreatePage";
import {
  readTaskDraft,
  writeTaskDraft,
} from "../src/features/task-create/taskDraftStorage";
import { renderWithServerState as render } from "./renderWithServerState";

const existingDraft = {
  step: 3,
  resumePreflight: true,
  dataEntryMode: "upload",
  selectedDataLabel: "我的导入资料",
  form: {
    title: "尚未完成的任务",
    dataset_version_id: "returns-draft",
    store: "合成店铺",
  },
  repairContext: { kind: "dataset", datasetKind: "products", returnToTask: true },
};
function createPage(query = {}, notify = vi.fn()) {
  return (
    <TaskCreatePage
      route={{ query }}
      notify={notify}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />
  );
}
function renderTemplate(notify = vi.fn()) {
  return render(createPage({ template_task: "task-template" }, notify));
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

test.each(["继续已有草稿", "关闭"])("已有草稿选择%s时完整保留输入", async (action) => {
  writeTaskDraft("user-1", existingDraft);
  apiProbe.task.mockResolvedValue({ id: "task-template", title: "模板任务" });
  renderTemplate();
  await screen.findByRole("dialog", { name: "保留已有任务草稿？" });
  expect(newTaskPageProbe).not.toHaveBeenCalled();
  expect(readTaskDraft("user-1")).toEqual(existingDraft);
  await userEvent.click(screen.getByRole("button", { name: action }));
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toEqual(existingDraft);
  expect(readTaskDraft("user-1")).toEqual(existingDraft);
});

test("取消覆盖可通过Escape保留原草稿", async () => {
  writeTaskDraft("user-1", existingDraft);
  apiProbe.task.mockResolvedValue({ id: "task-template", title: "模板任务" });
  renderTemplate();
  await screen.findByRole("dialog");
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toEqual(existingDraft);
});

test("明确确认后才以模板替换草稿，后续保存与完成清理仍可用", async () => {
  writeTaskDraft("user-1", existingDraft);
  apiProbe.task.mockResolvedValue({
    id: "task-template",
    title: "模板任务",
    config_version_id: "config-new",
  });
  renderTemplate();
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "替换草稿并创建类似任务" }));
  const props = newTaskPageProbe.mock.calls.at(-1)[0];
  expect(props.draft).toMatchObject({
    step: 1,
    resumePreflight: false,
    dataEntryMode: "mysql",
    form: {
      title: "模板任务（副本）",
      dataset_version_id: "",
      config_version_id: "config-new",
    },
  });
  expect(props.draft.repairContext).toBeUndefined();
  props.onDraftChange(props.draft);
  expect(readTaskDraft("user-1")).toEqual(props.draft);
  props.onDraftComplete();
  expect(readTaskDraft("user-1")).toBeNull();
});

test("模板读取失败继续原草稿且没有写存储副作用", async () => {
  writeTaskDraft("user-1", existingDraft);
  const setItem = vi.spyOn(Storage.prototype, "setItem");
  apiProbe.task.mockRejectedValue(new Error("合成读取失败"));
  const notify = vi.fn();
  renderTemplate(notify);
  await waitFor(() =>
    expect(notify).toHaveBeenCalledWith("无法读取原任务：合成读取失败", "error"),
  );
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toEqual(existingDraft);
  expect(setItem).not.toHaveBeenCalled();
  expect(readTaskDraft("user-1")).toEqual(existingDraft);
});

test("模板已选用后重复渲染不会覆盖后来保存的输入", async () => {
  apiProbe.task.mockResolvedValue({ id: "task-template", title: "模板任务" });
  const notify = vi.fn();
  const onNavigate = vi.fn();
  const props = {
    route: { query: { template_task: "task-template" } },
    notify,
    onNavigate,
    onChanged: vi.fn(),
    userId: "user-1",
  };
  const view = render(<TaskCreatePage {...props} />);
  await waitFor(() => expect(newTaskPageProbe).toHaveBeenCalled());
  newTaskPageProbe.mock.calls.at(-1)[0].onDraftChange(existingDraft);
  view.rerender(<TaskCreatePage {...props} notify={vi.fn()} />);
  expect(readTaskDraft("user-1")).toEqual(existingDraft);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  const page = newTaskPageProbe.mock.calls.at(-1)[0];
  page.onNavigate("data", existingDraft.repairContext);
  expect(readTaskDraft("user-1").repairContext).toEqual(existingDraft.repairContext);
  expect(onNavigate).toHaveBeenCalledWith("data", existingDraft.repairContext);
  page.onDiscard();
  expect(readTaskDraft("user-1")).toBeNull();
  expect(onNavigate).toHaveBeenCalledWith("tasks");
});

test("同一创建页切换到另一模板也先保护最新草稿", async () => {
  apiProbe.task.mockImplementation((id) => Promise.resolve({ id, title: "模板任务" }));
  const props = {
    notify: vi.fn(),
    onNavigate: vi.fn(),
    onChanged: vi.fn(),
    userId: "user-1",
  };
  const view = render(
    <TaskCreatePage {...props} route={{ query: { template_task: "first" } }} />,
  );
  await waitFor(() => expect(newTaskPageProbe).toHaveBeenCalled());
  newTaskPageProbe.mock.calls.at(-1)[0].onDraftChange(existingDraft);
  newTaskPageProbe.mockClear();
  view.rerender(
    <TaskCreatePage {...props} route={{ query: { template_task: "second" } }} />,
  );
  await screen.findByRole("dialog");
  expect(newTaskPageProbe).not.toHaveBeenCalled();
  expect(readTaskDraft("user-1")).toEqual(existingDraft);
});

test("旧数据源版本链接不再自动选数", () => {
  const notify = vi.fn();
  render(createPage({ dataset_version: "returns-v7" }, notify));
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toBeNull();
  expect(notify).toHaveBeenCalledWith(expect.stringContaining("入口已下线"), "error");
});

test("旧数据源草稿迁移后清除数据版本并保留其他输入", () => {
  writeTaskDraft("user-1", {
    step: 1,
    resumePreflight: false,
    form: {
      title: "待创建任务",
      dataset_version_id: "returns-v6",
    },
    dataEntryMode: "existing",
    selectedDataLabel: "当前完整数据",
  });

  render(createPage());

  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    dataEntryMode: "mysql",
    selectedDataLabel: "",
    form: { title: "待创建任务", dataset_version_id: "" },
  });
  expect(readTaskDraft("user-1")).toMatchObject({
    dataEntryMode: "mysql",
    selectedDataLabel: "",
    form: { dataset_version_id: "" },
  });
});

test("商品修复返回任务创建页时保留待恢复的退货版本", () => {
  writeTaskDraft("user-1", {
    step: 3,
    dataEntryMode: "mysql",
    resumePreflight: true,
    form: { dataset_version_id: "returns-v6" },
  });

  render(createPage());

  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    step: 3,
    resumePreflight: true,
    form: { dataset_version_id: "returns-v6" },
  });
});

test("创建类似任务时只继承名称和模型策略", async () => {
  apiProbe.task.mockResolvedValue({
    id: "task-template",
    title: "历史分析任务",
    dataset_name: "退货数据",
    dataset_version: 7,
    dataset_version_id: "returns-v7",
    product_version_id: "products-v3",
    config_version_id: "config-v2",
    snapshot: {
      config: {
        connection_id: "connection-1",
        cheap_model: "gpt-5.6-luna",
        cheap_effort: "low",
        primary_model: "gpt-5.6-terra",
        primary_effort: "medium",
        secondary_model: "gpt-5.6-sol",
        secondary_effort: "high",
        cheap_audit_percent: 10,
      },
    },
  });

  render(
    <TaskCreatePage
      route={{ query: { template_task: "task-template" } }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      userId="user-1"
    />,
  );

  expect(screen.queryByText("正在读取原任务配置…")).not.toBeInTheDocument();
  await waitFor(() => expect(newTaskPageProbe).toHaveBeenCalled());
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toMatchObject({
    step: 1,
    dataEntryMode: "mysql",
    selectedDataLabel: "",
    form: {
      title: "历史分析任务（副本）",
      dataset_version_id: "",
      product_version_id: "",
      config_version_id: "config-v2",
      store: "",
      listing: "",
      model_policy: {
        connection_id: "connection-1",
        cheap_model: "gpt-5.6-luna",
        primary_model: "gpt-5.6-terra",
        secondary_model: "gpt-5.6-sol",
      },
    },
  });
});

test("异步模板在首读可见后才打开确认并建立键盘焦点", async () => {
  writeTaskDraft("user-1", existingDraft);
  let resolveTemplate;
  apiProbe.task.mockReturnValue(
    new Promise((resolve) => {
      resolveTemplate = resolve;
    }),
  );
  render(
    <PageLoadingScope title="创建分析任务">
      {createPage({ template_task: "task-template" })}
    </PageLoadingScope>,
  );
  await act(async () => resolveTemplate({ id: "task-template", title: "模板任务" }));
  expect(screen.queryByRole("dialog", { hidden: true })).not.toBeInTheDocument();
  await screen.findByRole("dialog");
  expect(screen.getByRole("button", { name: "关闭" })).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(screen.getByRole("button", { name: "继续已有草稿" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(newTaskPageProbe.mock.calls.at(-1)[0].draft).toEqual(existingDraft);
});

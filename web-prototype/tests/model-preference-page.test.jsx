import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithServerState as render } from "./renderWithServerState";
const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    configs: vi.fn(),
    modelPreference: vi.fn(),
    saveModelPreference: vi.fn(),
  },
}));
vi.mock("../src/api", () => ({ api: apiMock }));
import { ModelPreferencePage } from "../src/features/system-settings/ModelPreferencePage";
import { navigateHash, useHashRoute } from "../src/app/hashRouter";

function PreferenceHarness({ notify }) {
  const { route, navigate } = useHashRoute();
  return (
    <>
      <output aria-label="页面">
        {route.page}:{route.query.tab}
      </output>
      <button onClick={() => navigate("analysis-tasks")}>侧栏任务</button>
      <button onClick={() => navigateHash("settings", { tab: "audit" })}>
        审计标签
      </button>
      {route.page === "settings" && route.query.tab === "model-preference" && (
        <ModelPreferencePage notify={notify} />
      )}
    </>
  );
}
beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  window.history.replaceState(null, "", "#settings?tab=model-preference");
  apiMock.configs.mockResolvedValue([
    {
      id: "connection",
      name: "合成服务",
      active_version_id: "version",
      models: [
        {
          id: "model",
          model_key: "main",
          display_name: "合成模型",
          active: true,
          validation_status: "validated",
          supported_efforts: ["medium", "high"],
        },
      ],
    },
  ]);
  apiMock.modelPreference.mockResolvedValue({
    connection_id: "connection",
    primary_model: "main",
    primary_effort: "medium",
  });
  apiMock.saveModelPreference.mockImplementation(async (policy) => policy);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});
async function startEditing(notify = vi.fn()) {
  render(<PreferenceHarness notify={notify} />);
  const effort = await screen.findByLabelText("主分析推理强度");
  await userEvent.selectOptions(effort, "high");
  return effort;
}

test.each(["侧栏任务", "审计标签"])(
  "%s离开先确认，继续或Esc不丢输入",
  async (entry) => {
    const effort = await startEditing();
    await userEvent.click(screen.getByRole("button", { name: entry }));
    expect(screen.getByRole("dialog", { name: "模型偏好尚未保存" })).toBeVisible();
    expect(window.location.hash).toBe("#settings?tab=model-preference");
    await userEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(effort).toHaveValue("high");
    await userEvent.click(screen.getByRole("button", { name: entry }));
    await userEvent.keyboard("{Escape}");
    expect(effort).toHaveValue("high");
    expect(apiMock.saveModelPreference).not.toHaveBeenCalled();
  },
);
test("改回原值不再提示，未保存时刷新触发浏览器原生保护", async () => {
  const effort = await startEditing();
  const dirtyClose = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(dirtyClose);
  expect(dirtyClose.defaultPrevented).toBe(true);
  await userEvent.selectOptions(effort, "medium");
  expect(screen.getByRole("button", { name: "撤销修改" })).toBeDisabled();
  const cleanClose = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(cleanClose);
  expect(cleanClose.defaultPrevented).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "侧栏任务" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByLabelText("页面")).toHaveTextContent("analysis-tasks");
});
test("放弃只离开，不保存偏好", async () => {
  await startEditing();
  await userEvent.click(screen.getByRole("button", { name: "审计标签" }));
  await userEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  expect(screen.getByLabelText("页面")).toHaveTextContent("settings:audit");
  expect(apiMock.saveModelPreference).not.toHaveBeenCalled();
});
test("保存后离开等待成功，失败留原页可重试且保留输入", async () => {
  const notify = vi.fn();
  const effort = await startEditing(notify);
  apiMock.saveModelPreference.mockRejectedValueOnce(new Error("合成保存失败"));
  await userEvent.click(screen.getByRole("button", { name: "侧栏任务" }));
  await userEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() => expect(notify).toHaveBeenCalledWith("合成保存失败", "error"));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toHaveFocus(),
  );
  expect(effort).toHaveValue("high");
  expect(screen.getByRole("dialog")).toBeVisible();
  let finish;
  apiMock.saveModelPreference.mockImplementationOnce(
    (policy) =>
      new Promise((resolve) => {
        finish = () => resolve(policy);
      }),
  );
  await userEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  expect(
    within(screen.getByRole("dialog")).getByRole("button", { name: "保存中…" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "放弃修改并离开" })).toBeDisabled();
  expect(window.location.hash).toBe("#settings?tab=model-preference");
  await act(async () => finish());
  await waitFor(() =>
    expect(screen.getByLabelText("页面")).toHaveTextContent("analysis-tasks"),
  );
  expect(apiMock.saveModelPreference).toHaveBeenLastCalledWith(
    expect.objectContaining({ primary_effort: "high" }),
  );
});

test("浏览器返回取消后恢复原历史位置，放弃后可正常前进", async () => {
  window.history.replaceState({ other: "保留键" }, "", "#analysis-tasks");
  navigateHash("settings", { tab: "model-preference" });
  await startEditing();
  act(() => window.history.back());
  await screen.findByRole("dialog");
  await waitFor(() =>
    expect(window.location.hash).toBe("#settings?tab=model-preference"),
  );
  await userEvent.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByLabelText("主分析推理强度")).toHaveValue("high");
  act(() => window.history.back());
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  await waitFor(() =>
    expect(screen.getByLabelText("页面")).toHaveTextContent("analysis-tasks"),
  );
  act(() => window.history.forward());
  expect(await screen.findByLabelText("主分析推理强度")).toHaveValue("medium");
  expect(window.history.state.other).toBe("保留键");
});

test("浏览器前进也保护草稿，保存成功后前往原目标", async () => {
  navigateHash("settings", { tab: "model-preference" });
  navigateHash("settings", { tab: "audit" });
  window.history.back();
  await waitFor(() =>
    expect(window.location.hash).toBe("#settings?tab=model-preference"),
  );
  await startEditing();
  act(() => window.history.forward());
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(screen.getByLabelText("页面")).toHaveTextContent("settings:audit"),
  );
  expect(apiMock.saveModelPreference).toHaveBeenCalledTimes(1);
});

test("直接修改URL也不静默丢失草稿，确认后到达原地址", async () => {
  await startEditing();
  act(() => {
    window.location.hash = "#analysis-tasks";
  });
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
  await waitFor(() =>
    expect(screen.getByLabelText("页面")).toHaveTextContent("analysis-tasks"),
  );
});

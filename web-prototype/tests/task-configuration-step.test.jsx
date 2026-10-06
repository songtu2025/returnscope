import { createRef } from "react";
import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { TaskConfigurationStep } from "../src/features/task-create/TaskConfigurationStep";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => cleanup());

function configuration(changes = {}) {
  return {
    headingRef: createRef(),
    form: { title: "合成任务", config_version_id: "config-1" },
    onFormChange: vi.fn(),
    publishedConfigs: [
      { id: "config-1", connection_name: "合成接入一", version: 1 },
      { id: "config-2", connection_name: "合成接入二", version: 2 },
    ],
    selectedConfig: { connection_name: "合成接入一" },
    availableModels: [
      {
        id: "model-1",
        model_key: "primary",
        display_name: "合成主模型",
        supported_efforts: ["low", "high"],
      },
      {
        id: "model-2",
        model_key: "replacement",
        display_name: "合成替换模型",
        supported_efforts: ["medium"],
      },
    ],
    modelPolicy: {
      primary_model: "primary",
      primary_effort: "high",
      cheap_model: "",
      cheap_effort: "low",
      secondary_model: "",
      secondary_effort: "medium",
    },
    onConnectionChange: vi.fn(),
    onModelPolicyChange: vi.fn(),
    ...changes,
  };
}

async function showSettings(user) {
  await user.click(screen.getByText("更改设置"));
}

function modelStage(label) {
  return [...document.querySelectorAll(".task-model-policy-grid > label")].find(
    (item) => item.textContent.startsWith(label),
  );
}

test.each([
  ["high", ["high", "low"], "high"],
  ["high", ["low"], "low"],
  ["high", [], "medium"],
  ["low", ["medium", "high"], "medium"],
])(
  "更换模型时保留支持的强度，否则使用首个支持值或中等：%s/%s",
  async (effort, supported, expected) => {
    const user = userEvent.setup();
    const props = configuration();
    props.modelPolicy.primary_effort = effort;
    props.availableModels[1].supported_efforts = supported;
    render(<TaskConfigurationStep {...props} />);
    await showSettings(user);
    await user.selectOptions(
      within(modelStage("主分析")).getAllByRole("combobox")[0],
      "replacement",
    );
    expect(props.onModelPolicyChange).toHaveBeenCalledExactlyOnceWith({
      primary_model: "replacement",
      primary_effort: expected,
    });
  },
);

test("可选模型可以停用，主分析必选，强度修改只更新对应字段", async () => {
  const user = userEvent.setup();
  const props = configuration();
  props.modelPolicy.cheap_model = "primary";
  render(<TaskConfigurationStep {...props} />);
  await showSettings(user);
  const primary = within(modelStage("主分析"));
  expect(primary.queryByRole("option", { name: "不启用" })).not.toBeInTheDocument();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "主分析推理强度" }),
    "low",
  );
  expect(props.onModelPolicyChange).toHaveBeenLastCalledWith({ primary_effort: "low" });
  await user.selectOptions(
    within(modelStage("低成本初筛")).getAllByRole("combobox")[0],
    "",
  );
  expect(props.onModelPolicyChange).toHaveBeenLastCalledWith({
    cheap_model: "",
    cheap_effort: "medium",
  });
});

test("名称、接入、数字比例与标题焦点引用保留各自回调", async () => {
  const user = userEvent.setup();
  const props = configuration();
  render(
    <TaskConfigurationStep {...props}>
      <button type="button">合成子操作</button>
    </TaskConfigurationStep>,
  );
  const title = screen.getByRole("textbox", { name: "任务名称" });
  expect(title).toHaveAttribute("maxlength", "120");
  await user.clear(title);
  expect(props.onFormChange).toHaveBeenLastCalledWith({ ...props.form, title: "" });
  expect(props.headingRef.current).toBe(
    screen.getByRole("heading", { name: "确认并开始分析" }),
  );
  expect(props.headingRef.current).toHaveAttribute("tabindex", "-1");
  expect(screen.getByRole("button", { name: "合成子操作" })).toBeVisible();
  await showSettings(user);
  const connection = [...document.querySelectorAll(".task-advanced-body > label")][0];
  await user.selectOptions(within(connection).getByRole("combobox"), "config-2");
  expect(props.onConnectionChange).toHaveBeenCalledExactlyOnceWith("config-2");
  const ratio = screen.getByRole("spinbutton");
  expect(ratio).toHaveValue(5);
  expect(ratio).toHaveAttribute("min", "0");
  expect(ratio).toHaveAttribute("max", "100");
  await user.clear(ratio);
  expect(props.onModelPolicyChange).toHaveBeenLastCalledWith({
    cheap_audit_percent: 0,
  });
});

test("已保存零抽检比例不会被默认值覆盖，未列出模型与自定义强度保留原显示", async () => {
  const user = userEvent.setup();
  const props = configuration({ availableModels: [], selectedConfig: undefined });
  props.modelPolicy = {
    ...props.modelPolicy,
    primary_model: "合成未列出模型",
    primary_effort: "合成自定义强度",
    cheap_audit_percent: 0,
  };
  render(<TaskConfigurationStep {...props} />);
  expect(screen.getByText("合成未列出模型", { selector: "strong" })).toBeVisible();
  expect(screen.getByText(/推理强度合成自定义强度/)).toBeVisible();
  await showSettings(user);
  expect(screen.getByRole("spinbutton")).toHaveValue(0);
});

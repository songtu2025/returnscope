import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ModelCatalogRow } from "../src/features/system-settings/ModelCatalogRow";

afterEach(() => cleanup());

function renderRow(overrides = {}) {
  const props = {
    model: {
      id: "first",
      model_key: "first",
      display_name: "测试模型",
      active: true,
      validation_status: "draft",
      supported_efforts: ["medium"],
    },
    selectedConnection: { id: "connection" },
    busy: "",
    validationActive: false,
    onValidateModel: vi.fn(),
    onOpenModelEditor: vi.fn(),
    onToggleModel: vi.fn(),
    ...overrides,
  };
  return { ...render(<ModelCatalogRow {...props} />), props };
}

test.each(["draft", "failed", "validated", "inactive"])(
  "%s 模型操作主次明确且作用于当前模型",
  async (status) => {
    const user = userEvent.setup();
    const model = {
      id: "target",
      model_key: "target",
      display_name: "目标模型",
      active: status !== "inactive",
      validation_status: status,
      supported_efforts: ["medium"],
    };
    const { props } = renderRow({ model });
    const primary = ["draft", "failed"].includes(status) ? "验证" : "编辑";
    expect(screen.getByRole("button", { name: primary })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: model.active ? "停用" : "启用" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: primary }));
    expect(
      primary === "验证" ? props.onValidateModel : props.onOpenModelEditor,
    ).toHaveBeenCalledExactlyOnceWith(model);
    await user.click(screen.getByLabelText("更多模型操作：目标模型"));
    await user.click(
      screen.getByRole("button", { name: model.active ? "停用" : "启用" }),
    );
    expect(props.onToggleModel).toHaveBeenCalledExactlyOnceWith(model);
    expect(screen.getByLabelText("更多模型操作：目标模型")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  },
);

test("菜单键盘打开、移动、关闭并恢复焦点", async () => {
  const user = userEvent.setup();
  renderRow();
  const trigger = screen.getByLabelText("更多模型操作：测试模型");
  trigger.focus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("button", { name: "编辑" })).toHaveFocus();
  await user.keyboard("{ArrowDown}");
  expect(screen.getByRole("button", { name: "停用" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});

test("处理中禁用主操作和更多，草稿连接不暴露验证", async () => {
  const user = userEvent.setup();
  const view = renderRow({ busy: "model-save" });
  const trigger = screen.getByLabelText("更多模型操作：测试模型");
  expect(screen.getByRole("button", { name: "验证" })).toBeDisabled();
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  view.rerender(<ModelCatalogRow {...view.props} busy="" selectedConnection={null} />);
  expect(screen.queryByRole("button", { name: "验证" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑" })).toBeEnabled();
});

test("运行中验证仅标注目标模型，结束后恢复，配置验证不误标模型", () => {
  const props = {
    selectedConnection: { id: "connection" },
    busy: "",
    validationActive: true,
    validationRun: { kind: "model", target_id: "first" },
    onValidateModel: vi.fn(),
    onOpenModelEditor: vi.fn(),
    onToggleModel: vi.fn(),
  };
  const rows = (overrides = {}) =>
    ["first", "second"].map((id) => (
      <ModelCatalogRow
        key={id}
        {...props}
        {...overrides}
        model={{
          id,
          model_key: id,
          display_name: id,
          active: true,
          supported_efforts: ["medium"],
          validation_status: "draft",
        }}
      />
    ));
  const view = render(rows());
  expect(screen.getAllByRole("button", { name: "验证中…" })).toHaveLength(1);
  expect(screen.getByRole("button", { name: "验证中…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "验证" })).toBeDisabled();
  view.rerender(rows({ validationActive: false }));
  expect(screen.getAllByRole("button", { name: "验证" })).toHaveLength(2);
  screen
    .getAllByRole("button", { name: "验证" })
    .forEach((button) => expect(button).toBeEnabled());
  view.rerender(rows({ validationRun: { kind: "config", target_id: "first" } }));
  expect(screen.queryByRole("button", { name: "验证中…" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "验证" })).toHaveLength(2);
});

test("已验证模型启动与运行期间主列显示进度，结束后恢复编辑", () => {
  const model = {
    id: "first",
    model_key: "first",
    display_name: "测试模型",
    active: true,
    validation_status: "validated",
    supported_efforts: ["medium"],
  };
  const view = renderRow({ model, busy: "model-validation-start-first" });
  expect(screen.getByRole("button", { name: "启动中…" })).toBeDisabled();
  view.rerender(
    <ModelCatalogRow
      {...view.props}
      busy=""
      validationActive={true}
      validationRun={{ kind: "model", target_id: "first" }}
    />,
  );
  expect(screen.getByRole("button", { name: "验证中…" })).toBeDisabled();
  view.rerender(<ModelCatalogRow {...view.props} busy="" />);
  expect(screen.getByRole("button", { name: "编辑" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "验证" })).not.toBeInTheDocument();
});

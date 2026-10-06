import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
const { mysqlProps } = vi.hoisted(() => ({ mysqlProps: vi.fn() }));

vi.mock("../src/features/task-create/MysqlReturnImportForm", () => ({
  MysqlReturnImportForm: (props) => {
    mysqlProps(props);
    return (
      <label>
        合成数据库草稿
        <input defaultValue="保留草稿" />
      </label>
    );
  },
}));

import { TaskDataStep } from "../src/features/task-create/TaskDataStep";
import { renderWithServerState as render } from "./renderWithServerState";

afterEach(() => cleanup());

function dataStep(changes = {}) {
  return {
    form: { title: "合成任务", dataset_version_id: "returns-1" },
    onFormChange: vi.fn(),
    returns: [
      { version_id: "returns-1", dataset_name: "合成反馈一", row_count: 1200 },
      { version_id: "returns-2", dataset_name: "合成反馈二", row_count: 0 },
    ],
    selectedReturns: undefined,
    dataEntryMode: "existing",
    selectedDataLabel: "合成数据范围",
    onDataEntryModeChange: vi.fn(),
    onSelectedDataLabelChange: vi.fn(),
    onUploadReturns: vi.fn(),
    mysqlDraft: { store: "合成店铺" },
    onMysqlDraftChange: vi.fn(),
    onMysqlDone: vi.fn(),
    onMysqlStateChange: vi.fn(),
    onInvalidateMysql: vi.fn(),
    busy: false,
    prepared: false,
    scopeLabel: "合成已准备范围",
    ...changes,
  };
}

test("选择已有数据先更新表单，再同步范围标签，清空选择保留其他字段", async () => {
  const user = userEvent.setup();
  const order = [];
  const props = dataStep({
    onFormChange: vi.fn((value) => order.push(["form", value])),
    onSelectedDataLabelChange: vi.fn((value) => order.push(["label", value])),
  });
  render(<TaskDataStep {...props} />);
  const select = screen.getByRole("combobox", { name: "已有数据源" });
  expect(
    within(select).getByRole("option", { name: "合成反馈一 · 1,200 条记录" }),
  ).toBeInTheDocument();
  await user.selectOptions(select, "returns-2");
  expect(order).toEqual([
    ["form", { ...props.form, dataset_version_id: "returns-2" }],
    ["label", "当前完整数据"],
  ]);
  await user.selectOptions(select, "");
  expect(order.slice(2)).toEqual([
    ["form", { ...props.form, dataset_version_id: "" }],
    ["label", ""],
  ]);
});

test("空数据给出导入路径，来源选择沿用对应回调和选中状态", async () => {
  const user = userEvent.setup();
  const props = dataStep({ returns: [] });
  render(<TaskDataStep {...props} />);
  expect(
    screen.getByText("还没有保存的数据，可以从数据库读取或上传文件。"),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "已有数据" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await user.click(screen.getByRole("button", { name: "上传文件" }));
  expect(props.onDataEntryModeChange).toHaveBeenCalledExactlyOnceWith("upload");
});

test.each([false, true])(
  "上传按钮显示文件与计数并沿用回调，有选择=%s",
  async (selected) => {
    const user = userEvent.setup();
    const props = dataStep({
      dataEntryMode: "upload",
      selectedReturns: selected
        ? { dataset_name: "合成上传", row_count: 0 }
        : undefined,
    });
    render(<TaskDataStep {...props} />);
    if (selected) expect(screen.getByText("合成数据范围 · 0 条记录")).toBeVisible();
    else
      expect(
        screen.getByText("上传 CSV 或 XLSX，系统会识别字段并检查数据。"),
      ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: selected ? "更换文件" : "选择文件" }),
    );
    expect(props.onUploadReturns).toHaveBeenCalledOnce();
  },
);

test.each(["mysql", "upload", "existing"])(
  "忙碌状态禁用来源和当前数据操作：%s",
  (mode) => {
    render(<TaskDataStep {...dataStep({ busy: true, dataEntryMode: mode })} />);
    const group = screen.getByRole("group", { name: "数据来源" });
    for (const button of within(group).getAllByRole("button"))
      expect(button).toBeDisabled();
    if (mode === "upload")
      expect(screen.getByRole("button", { name: "选择文件" })).toBeDisabled();
    if (mode === "existing") expect(screen.getByRole("combobox")).toBeDisabled();
    if (mode === "mysql") expect(mysqlProps.mock.calls.at(-1)[0].disabled).toBe(true);
  },
);

test("准备后的折叠只隐藏数据库表单，重开保留节点与草稿，取消准备复位折叠", async () => {
  const user = userEvent.setup();
  const props = dataStep({ dataEntryMode: "mysql" });
  const view = render(
    <TaskDataStep {...props}>
      <button type="button">合成子操作</button>
    </TaskDataStep>,
  );
  const draft = screen.getByRole("textbox", { name: "合成数据库草稿" });
  await user.clear(draft);
  await user.type(draft, "已修改草稿");
  view.rerender(<TaskDataStep {...props} prepared />);
  expect(draft).toBeInTheDocument();
  expect(draft).not.toBeVisible();
  const toggle = screen.getByRole("button", { name: "查看或修改数据" });
  expect(toggle).toHaveAttribute("aria-controls", "task-source-controls");
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await user.click(toggle);
  expect(screen.getByRole("textbox", { name: "合成数据库草稿" })).toBe(draft);
  expect(draft).toHaveValue("已修改草稿");
  expect(mysqlProps.mock.calls.at(-1)[0]).toEqual({
    draft: props.mysqlDraft,
    onDraftChange: props.onMysqlDraftChange,
    onDone: props.onMysqlDone,
    onStateChange: props.onMysqlStateChange,
    onInvalidate: props.onInvalidateMysql,
    prepared: true,
    disabled: false,
  });
  view.rerender(<TaskDataStep {...props} />);
  expect(draft).toBeVisible();
  view.rerender(<TaskDataStep {...props} prepared busy />);
  expect(screen.getByRole("button", { name: "查看或修改数据" })).toBeDisabled();
  expect(draft).not.toBeVisible();
});

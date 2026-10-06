import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const { completeProductCategories } = vi.hoisted(() => ({
  completeProductCategories: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: { completeProductCategories } }));

import { TaskCategoryCompletion } from "../src/features/data-management/TaskCategoryCompletion";
import { renderWithServerState as render } from "./renderWithServerState";

const categoryOptions = [
  { category_a: "合成品类A", category_b: "合成品类B", agent_family: "合成智能体" },
];

function mountCompletion() {
  const notify = vi.fn();
  const onReturnToTask = vi.fn();
  render(
    <TaskCategoryCompletion
      dataset={{ id: "synthetic-products", current_version: 4 }}
      focus={{
        store: "SYNTHETIC:US",
        taskTitle: "SYNTHETIC",
        blockedCommentCount: 10,
        categoryOptions,
        unresolvedProducts: [
          ["A", "ONE", true, "product_not_found"],
          ["B", "TWO", true, "missing_category"],
          ["C", "ONE", false, "missing_sku"],
        ].map(([msku, listing, editable, issue]) => ({
          product_key: msku,
          msku,
          suggested_listing: listing,
          editable,
          issue,
          comment_count: 3,
          record_count: 4,
        })),
      }}
      notify={notify}
      onReturnToTask={onReturnToTask}
    />,
  );
  return { notify, onReturnToTask };
}

beforeEach(() => {
  completeProductCategories.mockReset();
});
afterEach(() => cleanup());

async function fillOne(user) {
  await user.selectOptions(screen.getByLabelText("A 品类"), "0");
  await user.clear(screen.getByLabelText("修改原因"));
  await user.type(screen.getByLabelText("修改原因"), "  合成修改原因  ");
}

test("筛选批量补品类仅修改可编辑已选商品，并保留隐藏选择", async () => {
  const user = userEvent.setup();
  mountCompletion();
  expect(screen.getByLabelText("选择 C")).toBeDisabled();
  expect(screen.getByLabelText("C Listing")).toBeDisabled();
  expect(screen.getByLabelText("C 品类")).toBeDisabled();
  await user.click(screen.getByLabelText("选择 B"));
  await user.selectOptions(screen.getByLabelText("按 Listing 分组"), "ONE");
  await user.click(screen.getByRole("button", { name: "选择当前 2 个" }));
  expect(screen.getByLabelText("选择 A")).toBeChecked();
  expect(screen.getByLabelText("选择 C")).not.toBeChecked();
  await user.selectOptions(screen.getByLabelText("批量设置品类"), "0");
  await user.click(screen.getByRole("button", { name: "应用到已选 2 个" }));
  await user.selectOptions(screen.getByLabelText("按 Listing 分组"), "all");
  expect(screen.getByLabelText("A 品类")).toHaveValue("0");
  expect(screen.getByLabelText("B 品类")).toHaveValue("0");
  expect(screen.getByLabelText("C 品类")).toHaveValue("");
  expect(screen.getByLabelText("选择 B")).not.toBeChecked();
  expect(screen.getByLabelText("批量设置品类")).toHaveValue("");
  expect(screen.getByText("6/10")).toBeVisible();
});

test("提交保持版本、店铺、修改原因和完成商品范围，返回新版本", async () => {
  const user = userEvent.setup();
  const { notify, onReturnToTask } = mountCompletion();
  completeProductCategories.mockResolvedValue({
    current_version: 5,
    versions: [
      { version: 4, id: "synthetic-old" },
      { version: 5, id: "synthetic-new" },
    ],
  });
  await fillOne(user);
  await user.click(screen.getByRole("button", { name: "保存 1 个商品并重新预检" }));
  await waitFor(() => expect(onReturnToTask).toHaveBeenCalledWith("synthetic-new"));
  expect(completeProductCategories).toHaveBeenCalledExactlyOnceWith(
    "synthetic-products",
    {
      expected_version: 4,
      store: "SYNTHETIC:US",
      items: [
        {
          msku: "A",
          listing: "ONE",
          category_a: "合成品类A",
          category_b: "合成品类B",
          product_name: "",
        },
      ],
      change_note: "合成修改原因",
    },
  );
  expect(notify).toHaveBeenCalledWith("已补充 1 个商品，并创建产品信息 v5");
});

test.each([
  [409, "产品信息已被其他用户修改，请刷新后重新提交"],
  [500, "合成保存失败"],
])("保存失败保留填写内容且不能返回任务：%s", async (status, message) => {
  const user = userEvent.setup();
  const { notify, onReturnToTask } = mountCompletion();
  completeProductCategories.mockRejectedValue(
    Object.assign(new Error(message), { status }),
  );
  await fillOne(user);
  await user.click(screen.getByRole("button", { name: "保存 1 个商品并重新预检" }));
  await waitFor(() => expect(notify).toHaveBeenCalledWith(message, "error"));
  expect(onReturnToTask).not.toHaveBeenCalled();
  expect(screen.getByLabelText("A 品类")).toHaveValue("0");
  expect(screen.getByLabelText("修改原因")).toHaveValue("  合成修改原因  ");
  expect(screen.getByRole("button", { name: "保存 1 个商品并重新预检" })).toBeEnabled();
});

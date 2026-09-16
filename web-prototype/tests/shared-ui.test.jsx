import { useState } from "react";
import { ListChecks } from "@phosphor-icons/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";

import { EmptyState, InlineLoading, Modal } from "../src/components/SharedUi";

afterEach(() => cleanup());

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>打开弹窗</button>
      {open && (
        <Modal title="焦点测试" onClose={() => setOpen(false)}>
          <button>确认操作</button>
        </Modal>
      )}
    </>
  );
}

test("公共弹窗约束焦点并在各种关闭方式后恢复触发点", async () => {
  const user = userEvent.setup();
  render(<ModalHarness />);
  const trigger = screen.getByRole("button", { name: "打开弹窗" });

  await user.click(trigger);
  screen.getByRole("dialog", { name: "焦点测试" });
  const closeButton = screen.getByRole("button", { name: "关闭" });
  const confirmButton = screen.getByRole("button", { name: "确认操作" });
  expect(document.activeElement).toBe(closeButton);

  await user.tab({ shift: true });
  expect(document.activeElement).toBe(confirmButton);
  await user.tab();
  expect(document.activeElement).toBe(closeButton);

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "焦点测试" })).not.toBeInTheDocument();
  expect(document.activeElement).toBe(trigger);

  await user.click(trigger);
  fireEvent.mouseDown(screen.getByRole("dialog", { name: "焦点测试" }).parentElement);
  expect(screen.queryByRole("dialog", { name: "焦点测试" })).not.toBeInTheDocument();
  expect(document.activeElement).toBe(trigger);

  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "关闭" }));
  expect(screen.queryByRole("dialog", { name: "焦点测试" })).not.toBeInTheDocument();
  expect(document.activeElement).toBe(trigger);
});

test("公共空状态保留业务图标、说明和操作", () => {
  const { container } = render(
    <EmptyState
      icon={ListChecks}
      title="暂无复核任务"
      description="创建任务后会显示在这里。"
      action={<button type="button">创建任务</button>}
    />,
  );

  expect(container.firstChild).toHaveClass("ant-empty", "empty-state");
  expect(container.querySelector(".ant-empty-image svg")).toHaveAttribute(
    "width",
    "29",
  );
  expect(screen.getByText("暂无复核任务")).toBeVisible();
  expect(screen.getByText("创建任务后会显示在这里。")).toBeVisible();
  expect(screen.getByRole("button", { name: "创建任务" })).toBeEnabled();
});

test("公共行内加载态展示可访问的忙碌状态和文案", () => {
  const { container } = render(<InlineLoading label="正在读取复核批次…" />);

  expect(container.firstChild).toHaveClass("ant-spin", "inline-loading");
  expect(container.firstChild).toHaveAttribute("aria-busy", "true");
  expect(container.firstChild).toHaveAttribute("aria-live", "polite");
  expect(screen.getByText("正在读取复核批次…")).toBeVisible();
  expect(container.querySelector(".ant-spin-dot")).toBeInTheDocument();
});

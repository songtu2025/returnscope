import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";

import { Modal } from "../src/components/SharedUi";

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

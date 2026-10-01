import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { DashboardDetailEvidenceDrawer } from "../src/features/analysis-dashboards/DashboardDetailEvidenceDrawer";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";

afterEach(() => cleanup());

const record = {
  source_record_id: "test-record-1",
  order_id: "TEST-ORDER-1",
  comment: "用于焦点回归的模拟反馈",
  classification: {},
  comment_conclusions: [
    {
      topic_code: "TEST_TOPIC",
      topic_name: "测试标签",
      status: "NO_CONFIRMED",
      label_codes: [],
    },
  ],
};

const drawers = [
  [
    "分类结果",
    (props) => (
      <EvidenceDrawer
        {...props}
        group={{ record, member_count: 1, members: [] }}
        analysisContext="user_feedback"
      />
    ),
  ],
  [
    "分析看板",
    (props) => (
      <DashboardDetailEvidenceDrawer
        {...props}
        record={record}
        analysisContext="user_feedback"
      />
    ),
  ],
];

test.each(drawers)(
  "%s证据抽屉约束焦点，重渲染后保持焦点并恢复指定触发点",
  async (_, drawer) => {
    const user = userEvent.setup();
    render(
      <>
        <button>打开证据</button>
        <button>其他操作</button>
      </>,
    );
    const trigger = screen.getByRole("button", { name: "打开证据" });
    screen.getByRole("button", { name: "其他操作" }).focus();
    const returnFocusRef = { current: trigger };
    const onClose = vi.fn();
    const props = { onClose, returnFocusRef };
    const view = render(drawer(props));
    const dialog = screen.getByRole("dialog", { name: "分类结果与证据" });
    const closeButton = screen.getByRole("button", { name: "关闭证据抽屉" });
    const summary = dialog.querySelector("summary");
    expect(summary).not.toBeNull();
    expect(closeButton).toHaveFocus();

    const hiddenButton = document.createElement("button");
    hiddenButton.hidden = true;
    hiddenButton.textContent = "隐藏操作";
    dialog.append(hiddenButton);
    await user.tab({ shift: true });
    expect(summary).toHaveFocus();
    await user.tab();
    expect(closeButton).toHaveFocus();

    await user.tab();
    expect(summary).toHaveFocus();
    const latestOnClose = vi.fn();
    view.rerender(drawer({ ...props, onClose: latestOnClose }));
    expect(summary).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(latestOnClose).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(dialog);
    expect(latestOnClose).toHaveBeenCalledTimes(1);
    await user.click(closeButton);
    expect(latestOnClose).toHaveBeenCalledTimes(2);
    fireEvent.mouseDown(dialog.parentElement);
    expect(latestOnClose).toHaveBeenCalledTimes(3);

    view.unmount();
    expect(trigger).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(latestOnClose).toHaveBeenCalledTimes(3);
  },
);

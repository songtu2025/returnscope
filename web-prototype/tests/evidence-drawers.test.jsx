import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { DashboardDetailEvidenceDrawer } from "../src/features/analysis-dashboards/DashboardDetailEvidenceDrawer";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";
import { factPresentation } from "../src/features/classification-results/semanticResultPresentation";
import { resultLabelText } from "../src/lib/taxonomyPresentation";

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
    (props, source = record) => (
      <EvidenceDrawer
        {...props}
        group={{ record: source, member_count: 1, members: [] }}
        analysisContext="user_feedback"
      />
    ),
  ],
  [
    "分析看板",
    (props, source = record) => (
      <DashboardDetailEvidenceDrawer
        {...props}
        record={source}
        analysisContext="user_feedback"
      />
    ),
  ],
];

test.each(drawers)("%s证据复用事实标签中文路径，保留编码供核对", async (_, drawer) => {
  const path = ["尺码与适配", "不合脚", "偏小"];
  const source = {
    ...record,
    comment_conclusions: [
      {
        topic_code: "TEST",
        topic_path: ["尺码与适配"],
        status: "NEGATIVE",
        supporting_fact_ids: ["fact-1"],
      },
    ],
    classification: {
      primary_label_codes: ["TEST_FIT"],
      problem_label_codes: ["TEST_FIT"],
      semantic_units: [
        {
          fact_id: "fact-1",
          label_code: "TEST_FIT",
          full_label_path: path,
          part: "WHOLE_SHOE",
          causal_attribution: "UNKNOWN",
          evaluation_direction: "NEGATIVE",
          opinion: "尺寸偏小",
          evidence: "Too small",
        },
      ],
    },
  };
  render(drawer({ onClose: vi.fn(), returnFocusRef: { current: null } }, source));
  const context = screen.queryByText("业务标签与记录状态", { exact: true });
  if (context) await userEvent.click(context);
  expect(screen.getAllByTitle("TEST_FIT")[0]).toHaveTextContent(path.join(" → "));
  expect(screen.getByTitle("部位编码：WHOLE_SHOE")).toHaveTextContent("整鞋");
  expect(screen.getByTitle("因果归属编码：UNKNOWN")).toHaveTextContent("未明确");
});

test.each([
  ["WHOLE_SHOE", "整鞋"],
  ["FRAME", "镜框"],
  ["FINGER", "手指"],
  ["UNRECOGNIZED_PART", "UNRECOGNIZED_PART"],
])("不同品类及未知部位 %s 的中文展示不推断新含义", (part, label) => {
  expect(
    factPresentation({ part, causal_attribution: "UNRECOGNIZED_CAUSE" }),
  ).toMatchObject({
    partLabel: label,
    causalAttributionLabel: "UNRECOGNIZED_CAUSE",
  });
});

test("记录已有标签路径优先，未提供路径的编码保持原值", () => {
  expect(
    resultLabelText(
      { problem_label_paths: { FIT: ["已有中文"] } },
      ["FIT", "MISSING"],
      { FIT: ["事实中文"] },
    ),
  ).toBe("已有中文、MISSING");
});

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
    const summaries = dialog.querySelectorAll("summary");
    const summary = summaries[0];
    const lastSummary = summaries[summaries.length - 1];
    expect(summary).not.toBeNull();
    expect(closeButton).toHaveFocus();

    const hiddenButton = document.createElement("button");
    hiddenButton.hidden = true;
    hiddenButton.textContent = "隐藏操作";
    dialog.append(hiddenButton);
    await user.tab({ shift: true });
    expect(lastSummary).toHaveFocus();
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

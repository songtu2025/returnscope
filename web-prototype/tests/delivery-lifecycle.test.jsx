import { afterEach, expect, test, vi } from "vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { DeliveryLifecycleControls } from "../src/components/DeliveryLifecycleControls";
import { DashboardRow } from "../src/features/analysis-dashboards/DashboardRow";
import { ReportStatus } from "../src/features/analysis-dashboards/AiInsightReportCommon";
import { changeDeliveryLifecycle } from "../src/shared/api/deliveryApi";

vi.mock("../src/shared/api/deliveryApi", () => ({ changeDeliveryLifecycle: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test.each([
  ["result", "分类结果"],
  ["dashboard", "分析看板"],
  ["report", "报告"],
])("%s单项菜单支持键盘打开、关闭、确认及外部点击", async (kind, label) => {
  const user = userEvent.setup();
  render(
    <>
      <DeliveryLifecycleControls
        kind={kind}
        id={`${kind}-synthetic`}
        revision={2}
        name="合成对象"
      />
      <button type="button">外部操作</button>
    </>,
  );
  const trigger = screen.getByLabelText(`更多${label}操作：合成对象`);
  const action = screen.getByRole("button", { name: `删除${label}`, exact: true });
  trigger.focus();
  await user.keyboard("{ArrowDown}");
  expect(action).toHaveFocus();
  await user.keyboard("{ArrowDown}{ArrowUp}");
  expect(action).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(trigger).toHaveFocus();
  await user.keyboard("{ArrowUp}");
  expect(action).toHaveFocus();
  await user.keyboard("{Escape}{Enter}");
  expect(action).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByRole("dialog")).toHaveAccessibleName(`删除${label}：合成对象`);
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "返回" }));
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  const outside = screen.getByRole("button", { name: "外部操作" });
  await user.click(outside);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(outside).toHaveFocus();
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
});

test("删除前确认，引用冲突保留弹窗和错误，解除引用后可重试", async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  changeDeliveryLifecycle.mockRejectedValueOnce(new Error("关联看板：合成看板"));
  changeDeliveryLifecycle.mockResolvedValueOnce({ ok: true });
  render(
    <DeliveryLifecycleControls
      kind="result"
      id="result-synthetic"
      revision={3}
      name="合成结果"
      onChanged={changed}
    />,
  );
  await user.click(screen.getByLabelText("更多分类结果操作：合成结果"));
  await user.click(screen.getByRole("button", { name: "删除分类结果", exact: true }));
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "确认删除" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("合成看板");
  expect(screen.getByRole("button", { name: "确认删除" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(changed).toHaveBeenCalledOnce());
  expect(changeDeliveryLifecycle).toHaveBeenLastCalledWith(
    "result",
    "result-synthetic",
    "delete",
    3,
  );
});

test("已删除看板只有恢复入口，提交恢复不会启动生成", async () => {
  const user = userEvent.setup();
  changeDeliveryLifecycle.mockResolvedValue({ ok: true });
  render(
    <DeliveryLifecycleControls
      kind="dashboard"
      id="dashboard-synthetic"
      revision={4}
      name="合成看板"
      deleted
    />,
  );
  expect(screen.queryByText("确认删除")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "恢复分析看板" }));
  await waitFor(() =>
    expect(changeDeliveryLifecycle).toHaveBeenCalledWith(
      "dashboard",
      "dashboard-synthetic",
      "restore",
      4,
    ),
  );
});

test("运行中报告提供取消入口，取消后显示终态而非失败", async () => {
  const cancel = vi.fn();
  const props = {
    report: { id: "job", status: "running", attempt_no: 2 },
    latestReport: null,
    onSelect: vi.fn(),
    onRetry: vi.fn(),
    onCancel: cancel,
  };
  const view = render(<ReportStatus {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "取消本次生成" }));
  expect(cancel).toHaveBeenCalledOnce();
  view.rerender(
    <ReportStatus {...props} report={{ ...props.report, status: "cancelled" }} />,
  );
  expect(screen.getByText("本次生成已取消")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "取消本次生成" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
});

test("当前看板操作保留查看和更多，查看只打开当前对象", async () => {
  const open = vi.fn();
  render(
    <DashboardRow
      dashboard={{ id: "dashboard-synthetic", name: "合成看板" }}
      onOpen={open}
    />,
  );
  const actions = screen.getAllByRole("cell").at(-1);
  expect(within(actions).getByRole("button", { name: "查看" })).toBeVisible();
  expect(within(actions).getByLabelText("更多分析看板操作：合成看板")).toBeVisible();
  expect(
    within(actions).queryByRole("button", { name: "恢复分析看板" }),
  ).not.toBeInTheDocument();
  await userEvent.click(within(actions).getByRole("button", { name: "查看" }));
  expect(open).toHaveBeenCalledOnce();
  expect(changeDeliveryLifecycle).not.toHaveBeenCalled();
});

test("已删除看板查看与恢复独立，恢复中防止重复，失败后可重试", async () => {
  let rejectRestore;
  changeDeliveryLifecycle.mockReturnValueOnce(
    new Promise((_resolve, reject) => {
      rejectRestore = reject;
    }),
  );
  const open = vi.fn();
  render(
    <DashboardRow
      dashboard={{
        id: "dashboard-synthetic",
        name: "合成看板",
        deleted_at: "2026-10-15",
        revision: 4,
      }}
      onOpen={open}
    />,
  );
  const actions = screen.getAllByRole("cell").at(-1);
  expect(
    within(actions).queryByLabelText("更多分析看板操作：合成看板"),
  ).not.toBeInTheDocument();
  await userEvent.click(within(actions).getByRole("button", { name: "恢复分析看板" }));
  expect(within(actions).getByRole("button", { name: "正在恢复…" })).toBeDisabled();
  await userEvent.click(within(actions).getByRole("button", { name: "查看" }));
  expect(open).toHaveBeenCalledOnce();
  await act(async () => rejectRestore(new Error("合成恢复失败，请重试")));
  expect(within(actions).getByRole("alert")).toHaveTextContent("合成恢复失败，请重试");
  expect(within(actions).getByRole("button", { name: "恢复分析看板" })).toBeEnabled();
  changeDeliveryLifecycle.mockResolvedValueOnce({ ok: true });
  await userEvent.click(within(actions).getByRole("button", { name: "恢复分析看板" }));
  await waitFor(() =>
    expect(within(actions).queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(changeDeliveryLifecycle).toHaveBeenCalledTimes(2);
  expect(changeDeliveryLifecycle).toHaveBeenLastCalledWith(
    "dashboard",
    "dashboard-synthetic",
    "restore",
    4,
  );
});

import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithServerState as render } from "./renderWithServerState";
import { useHashRoute } from "../src/app/hashRouter";
import { AnalysisDashboardPage } from "../src/features/analysis-dashboards/AnalysisDashboardPage";

const { read } = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock("../src/shared/api/dashboardApi", () => ({
  dashboardApi: { analysisDashboards: read },
}));

function Harness() {
  const { route } = useHashRoute();
  return (
    <AnalysisDashboardPage route={route} notify={vi.fn()} userId="synthetic-user" />
  );
}

beforeEach(() => {
  read.mockReset().mockResolvedValue({
    items: [{ id: "synthetic-dashboard", name: "合成看板", status: "active" }],
    total: 120,
  });
  window.history.replaceState(
    null,
    "",
    "#analysis-dashboards?page=3&page_size=50&q=旧条件&status=archived",
  );
});
afterEach(cleanup);

test.each(["按钮", "回车"])(
  "草稿不覆盖生效条件，%s提交一致并回第一页",
  async (method) => {
    render(<Harness />);
    await screen.findByText("合成看板");
    const input = screen.getByRole("textbox", { name: "搜索分析看板" });
    await userEvent.clear(input);
    await userEvent.type(input, "新条件");
    await userEvent.selectOptions(screen.getByLabelText("看板状态"), "active");
    const applied = screen.getByRole("status", { name: "已生效看板筛选" });
    expect(applied).toHaveTextContent("关键词：旧条件");
    expect(applied).toHaveTextContent("看板状态：已归档");
    expect(applied).not.toHaveTextContent("新条件");
    expect(read).toHaveBeenCalledOnce();
    if (method === "按钮")
      await userEvent.click(screen.getByRole("button", { name: "筛选", exact: true }));
    else {
      input.focus();
      await userEvent.keyboard("{Enter}");
    }
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        { q: "新条件", status: "active", page: 1, page_size: 50 },
        {},
      ),
    );
    expect(applied).toHaveTextContent("关键词：新条件");
    expect(applied).toHaveTextContent("看板状态：可用");
    const query = new URLSearchParams(window.location.hash.split("?")[1]);
    expect(query.get("page_size")).toBe("50");
    expect(query.has("page")).toBe(false);
  },
);

test.each([false, true])(
  "正常态或空结果(%s)清除同一入口，重置草稿、URL及生效条件",
  async (empty) => {
    if (empty) read.mockResolvedValue({ items: [], total: 0 });
    render(<Harness />);
    await waitFor(() => expect(read).toHaveBeenCalled());
    const input = screen.getByRole("textbox", { name: "搜索分析看板" });
    await userEvent.clear(input);
    await userEvent.type(input, "未提交的草稿");
    await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(input).toHaveValue("");
    expect(screen.getByLabelText("看板状态")).toHaveValue("");
    expect(screen.queryByRole("status", { name: "已生效看板筛选" })).toBeNull();
    await waitFor(() =>
      expect(read).toHaveBeenLastCalledWith(
        { q: "", status: "", page: 1, page_size: 50 },
        {},
      ),
    );
    const query = new URLSearchParams(window.location.hash.split("?")[1]);
    for (const key of ["page", "q", "status"]) expect(query.has(key)).toBe(false);
    expect(query.get("page_size")).toBe("50");
  },
);

test("输入法组合Enter不提交，结束后正常提交", async () => {
  render(<Harness />);
  await screen.findByText("合成看板");
  const input = screen.getByRole("textbox", { name: "搜索分析看板" });
  fireEvent.compositionStart(input);
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.submit(input.closest("form"));
  expect(read).toHaveBeenCalledOnce();
  fireEvent.compositionEnd(input);
  for (const composition of [{ isComposing: true }, { keyCode: 229 }]) {
    const event = new KeyboardEvent("keydown", {
      key: "Enter",
      bubbles: true,
      cancelable: true,
      ...composition,
    });
    input.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  }
  await userEvent.type(input, "已组词{Enter}");
  await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
});

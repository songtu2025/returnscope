import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useHashRoute } from "../src/app/hashRouter";
import {
  classificationResultRouteState,
  writeClassificationResultRoute,
} from "../src/features/classification-results/classificationResultRoute";
import { ResultPoolFilters } from "../src/features/classification-results/ResultPoolFilters";
import { ResultPoolStatus } from "../src/features/classification-results/ResultPoolStatus";
import { useResultPoolWorkspace } from "../src/features/classification-results/useResultPoolWorkspace";

const { read } = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock(
  "../src/features/classification-results/useClassificationResultListData",
  () => ({ useClassificationResultListData: read }),
);
vi.mock("../src/features/classification-results/useResultSelection", () => ({
  useResultSelection: () => ({ selectedResults: [] }),
}));

function Harness() {
  const { route: hash } = useHashRoute();
  const route = classificationResultRouteState(hash.query);
  const updateRoute = (changes) =>
    writeClassificationResultRoute({ ...route, ...changes });
  const state = useResultPoolWorkspace({ route, updateRoute, userId: "test-user" });
  return (
    <>
      <ResultPoolFilters {...state} route={route} updateRoute={updateRoute} />
      <ResultPoolStatus {...state} />
    </>
  );
}

beforeEach(() => {
  window.history.replaceState(
    null,
    "",
    "#classification-results?page=3&q=旧条件&store_site=测试店铺&listing=TEST&quality_status=unusable",
  );
  read.mockReturnValue({
    data: { items: [{}], total: 100 },
    loading: false,
    error: "",
    load: vi.fn(),
  });
});
afterEach(cleanup);

test("草稿不改变已生效条件，点击与 Enter 提交均回第一页", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  const input = screen.getByRole("textbox", { name: "搜索分类结果" });
  await user.clear(input);
  await user.type(input, "新条件");
  const summary = screen.getByRole("status", { name: "已生效筛选" });
  expect(summary).toHaveTextContent("关键词：旧条件");
  expect(summary).not.toHaveTextContent("新条件");
  expect(read.mock.lastCall[0].q).toBe("旧条件");
  await user.click(screen.getByRole("button", { name: "筛选", exact: true }));
  expect(new URLSearchParams(window.location.hash.split("?")[1]).get("q")).toBe(
    "新条件",
  );
  expect(read.mock.lastCall[0]).toMatchObject({ q: "新条件", page: 1 });
  await user.clear(input);
  await user.type(input, "回车条件{Enter}");
  expect(read.mock.lastCall[0]).toMatchObject({ q: "回车条件", page: 1 });
  expect(summary).toHaveTextContent("关键词：回车条件");
});

test("清除同时重置输入、生效条件、URL 和页码，保留页大小", async () => {
  window.history.replaceState(
    null,
    "",
    `${window.location.hash}&page_size=50&lifecycle=deleted`,
  );
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(screen.getByRole("textbox", { name: "搜索分类结果" }), "未提交");
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(screen.getByRole("textbox", { name: "搜索分类结果" })).toHaveValue("");
  expect(screen.getByRole("textbox", { name: "店铺或站点" })).toHaveValue("");
  expect(screen.getByRole("textbox", { name: "Listing" })).toHaveValue("");
  expect(screen.queryByRole("status", { name: "已生效筛选" })).not.toBeInTheDocument();
  expect(read.mock.lastCall[0]).toEqual({
    q: "",
    store_site: "",
    listing: "",
    quality_status: "",
    page: 1,
    page_size: 50,
  });
  expect(window.location.hash).toBe("#classification-results?page_size=50");
});

test("无生效条件时也能清空未提交草稿", async () => {
  window.history.replaceState(null, "", "#classification-results");
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(screen.getByRole("textbox", { name: "搜索分类结果" }), "草稿");
  await user.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(screen.getByRole("textbox", { name: "搜索分类结果" })).toHaveValue("");
});

test("浏览器路由后退同步输入与生效条件，不保留其他路由的草稿", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.type(screen.getByRole("textbox", { name: "搜索分类结果" }), "草稿");
  await act(async () => {
    window.history.replaceState(null, "", "#classification-results?q=返回条件&page=2");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(screen.getByRole("textbox", { name: "搜索分类结果" })).toHaveValue("返回条件");
  expect(screen.getByRole("status", { name: "已生效筛选" })).toHaveTextContent(
    "关键词：返回条件",
  );
  expect(read.mock.lastCall[0]).toMatchObject({ q: "返回条件", page: 2 });
});

test("中文组合输入的 Enter 不提交，组合结束后可以正常提交", async () => {
  render(<Harness />);
  const input = screen.getByRole("textbox", { name: "搜索分类结果" });
  fireEvent.compositionStart(input);
  fireEvent.change(input, { target: { value: "中文" } });
  expect(
    fireEvent.keyDown(input, {
      key: "Enter",
      code: "Enter",
      isComposing: true,
      keyCode: 229,
    }),
  ).toBe(false);
  fireEvent.submit(screen.getByRole("form", { name: "分类结果筛选" }));
  expect(read.mock.lastCall[0].q).toBe("旧条件");
  fireEvent.compositionEnd(input);
  await userEvent.setup().type(input, "{Enter}");
  expect(read.mock.lastCall[0].q).toBe("中文");
});

test("筛选无结果沿用同一清除操作", async () => {
  read.mockReturnValue({
    data: { items: [], total: 0 },
    loading: false,
    error: "",
    load: vi.fn(),
  });
  render(<Harness />);
  const empty = screen.getByText("没有符合条件的结果").closest(".empty-state");
  await userEvent
    .setup()
    .click(within(empty).getByRole("button", { name: "清除筛选" }));
  expect(read.mock.lastCall[0]).toMatchObject({ q: "", listing: "", page: 1 });
  expect(screen.getByRole("textbox", { name: "搜索分类结果" })).toHaveValue("");
});

test("记录情况选择后保持草稿，只有显式提交才生效", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("combobox", { name: "记录情况" }));
  await user.click(
    screen.getByText("含待复核记录", { selector: ".ant-select-item-option-content" }),
  );
  expect(read.mock.lastCall[0].quality_status).toBe("unusable");
  expect(screen.getByRole("status", { name: "已生效筛选" })).toHaveTextContent(
    "含不可用记录",
  );
  await user.click(screen.getByRole("button", { name: "筛选", exact: true }));
  expect(read.mock.lastCall[0].quality_status).toBe("review_required");
  expect(screen.getByRole("status", { name: "已生效筛选" })).toHaveTextContent(
    "含待复核记录",
  );
});

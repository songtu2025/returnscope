import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { renderWithServerState as render } from "./renderWithServerState";
const { references, monitor } = vi.hoisted(() => ({
  references: vi.fn(),
  monitor: vi.fn(),
}));
vi.mock("../src/api", () => ({ api: { dataVersionReferences: references } }));
vi.mock("../src/features/task-runtime/TaskMonitor", () => ({
  TaskMonitor: (props) => {
    monitor(props);
    return props.onReturnProducts ? (
      <button onClick={props.onReturnProducts}>返回产品信息</button>
    ) : (
      <span>普通任务</span>
    );
  },
}));
import { DatasetReferences } from "../src/features/data-management/DatasetReferences";
import { TaskRuntimePage } from "../src/features/task-runtime/TaskRuntimePage";
import { productReferenceReturnQuery } from "../src/features/data-management/productReferenceRoute";
import {
  buildHash,
  navigateHash,
  parseHash,
  useHashRoute,
} from "../src/app/hashRouter";
import { routeForDestination } from "../src/app/navigation";

const sourceQuery = {
  tab: "impact",
  view: "products",
  dataset: "synthetic-products",
  rows_q: "合成搜索",
  rows_store: "STORE",
  rows_category: "水鞋",
  rows_page: "7",
  rows_page_size: "50",
  reference_page: "3",
};
function Harness() {
  const { route } = useHashRoute();
  const position = useRef(null);
  const navigate = (destination, focus) => {
    const next = routeForDestination(destination, focus);
    navigateHash(next.page, next.query);
  };
  if (route.page === "analysis-tasks")
    return (
      <TaskRuntimePage
        route={route}
        notify={vi.fn()}
        onNavigate={navigate}
        onChanged={vi.fn()}
      />
    );
  return (
    <DatasetReferences
      currentVersionId="products-current"
      page={Number(route.query.reference_page) || 1}
      returnPosition={position}
      onNavigate={navigate}
    />
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  references.mockResolvedValue({
    items: [{ task_id: "task-one", title: "同名任务", reference_type: "products" }],
    total: 50,
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("产品引用任务往返恢复原路由、引用页、滚动与按钮焦点", async () => {
  window.location.hash = buildHash("data-assets", sourceQuery);
  const scroll = vi.spyOn(window, "scrollY", "get").mockReturnValue(480);
  render(<Harness />);
  const open = await screen.findByRole("button", { name: "查看任务" });
  open.focus();
  await userEvent.keyboard("{Enter}");
  expect(parseHash().query.task_id).toBe("task-one");
  const source = parseHash(parseHash().query.product_return);
  expect(source.page).toBe("data-assets");
  expect(source.query).toEqual(sourceQuery);
  await userEvent.click(screen.getByRole("button", { name: "返回产品信息" }));
  expect(parseHash().page).toBe("data-assets");
  expect(parseHash().query).toEqual(sourceQuery);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "查看任务" })).toHaveFocus(),
  );
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 480,
    left: 0,
    behavior: "auto",
  });
  expect(references).toHaveBeenLastCalledWith(
    "products-current",
    { page: 3, page_size: 20 },
    expect.any(Object),
  );
  scroll.mockRestore();
});

test.each([
  "#settings?tab=impact",
  "#data-assets?view=rules&tab=impact",
  "#data-assets?tab=rows",
  "#classification-results?tab=impact",
])("拒绝非产品引用返回地址 %s", (target) => {
  expect(productReferenceReturnQuery(parseHash(target))).toBeNull();
  render(
    <TaskRuntimePage
      route={{ query: { product_return: target } }}
      notify={vi.fn()}
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
    />,
  );
  expect(monitor.mock.calls.at(-1)[0].onReturnProducts).toBeUndefined();
});

test("返回仅保留产品查看条件，忽略动作字段且保留既有任务补资料来源", () => {
  expect(
    productReferenceReturnQuery({
      page: "data-assets",
      query: {
        ...sourceQuery,
        action: "delete",
        task_id: "other",
        return_to: "task-create",
      },
    }),
  ).toEqual({ ...sourceQuery, return_to: "task-create" });
});

test("引用消失时返回聚焦标题", async () => {
  window.location.hash = buildHash("data-assets", sourceQuery);
  const view = render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "查看任务" }));
  references.mockResolvedValue({ items: [], total: 0 });
  // 返回时模拟引用列表已变化，原入口已不存在。
  view.unmount();
  const saved = {
    current: {
      identity: JSON.stringify(["products-current", 3]),
      id: "task-one:products",
      top: 480,
      left: 0,
    },
  };
  render(
    <DatasetReferences
      currentVersionId="products-current"
      page={3}
      returnPosition={saved}
    />,
  );
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "任务引用" })).toHaveFocus(),
  );
});

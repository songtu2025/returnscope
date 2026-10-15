import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { PageLoadingContext } from "../src/hooks/usePageLoading";
import { useListReturnPosition } from "../src/hooks/useListReturnPosition";

function ListHarness({
  active = true,
  ready = true,
  initial = false,
  identity = "page=2&q=鞋",
  missing = false,
  snapshotRef,
}) {
  return (
    <PageLoadingContext value={{ initial, report: () => {} }}>
      <ListContent {...{ active, ready, identity, missing, snapshotRef }} />
    </PageLoadingContext>
  );
}
function ListContent({ active, ready, identity, missing, snapshotRef }) {
  const { containerRef, titleRef, remember } = useListReturnPosition({
    active,
    ready,
    identity,
    snapshotRef,
  });
  return (
    <div ref={containerRef} hidden={!active}>
      <h1 ref={titleRef} tabIndex={-1}>
        合成列表
      </h1>
      {!missing && (
        <button data-list-return-id="row-id" onClick={() => remember("row-id")}>
          查看合成记录
        </button>
      )}
    </div>
  );
}
beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  Object.defineProperty(window, "scrollY", { configurable: true, value: 640 });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
});

test("返回等待数据与首次区域可见，恢复滚动并聚焦原行且不再次滚动", () => {
  const view = render(<ListHarness />);
  fireEvent.click(screen.getByRole("button"));
  view.rerender(<ListHarness active={false} />);
  window.scrollTo.mockClear();
  view.rerender(<ListHarness ready={false} initial />);
  expect(window.scrollTo).not.toHaveBeenCalled();
  view.rerender(<ListHarness initial />);
  expect(window.scrollTo).not.toHaveBeenCalled();
  const focus = vi.spyOn(HTMLElement.prototype, "focus");
  view.rerender(<ListHarness />);
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 640,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("button")).toHaveFocus();
  expect(focus).toHaveBeenLastCalledWith({ preventScroll: true });
  window.scrollTo.mockClear();
  view.rerender(<ListHarness ready={false} />);
  view.rerender(<ListHarness />);
  expect(window.scrollTo).not.toHaveBeenCalled();
});

test.each(["page=3&q=鞋", "page=2&q=手套"])("身份变化%s不恢复旧位置", (identity) => {
  const view = render(<ListHarness />);
  fireEvent.click(screen.getByRole("button"));
  view.rerender(<ListHarness active={false} />);
  view.rerender(<ListHarness identity={identity} />);
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 0,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("button")).not.toHaveFocus();
});

test("原行已不存在则回到列表标题，不聚焦其他记录", () => {
  const view = render(<ListHarness />);
  fireEvent.click(screen.getByRole("button"));
  view.rerender(<ListHarness active={false} />);
  view.rerender(<ListHarness missing />);
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 0,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("heading")).toHaveFocus();
});

test("父级内存快照可跨列表卸载恢复，独立入口不沿用旧会话", () => {
  const snapshotRef = { current: null };
  const list = render(<ListHarness snapshotRef={snapshotRef} />);
  fireEvent.click(screen.getByRole("button"));
  list.unmount();
  const returned = render(<ListHarness snapshotRef={snapshotRef} />);
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 640,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("button")).toHaveFocus();
  expect(snapshotRef.current).toBeNull();
  returned.unmount();
  render(<ListHarness />);
  expect(window.scrollTo).toHaveBeenLastCalledWith({
    top: 0,
    left: 0,
    behavior: "auto",
  });
  expect(screen.getByRole("button")).not.toHaveFocus();
});

import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { requestNavigation } from "../src/app/navigationGuard";
import { useUnsavedNavigation } from "../src/hooks/useUnsavedNavigation";
import { UnsavedChangesDialog } from "../src/components/UnsavedChangesActions";

afterEach(cleanup);

test("普通保存期间请求离开，保存成功后自动继续目标且不重复保存", () => {
  const save = vi.fn();
  const proceed = vi.fn();
  const { result, rerender } = renderHook(
    ({ dirty, busy }) => useUnsavedNavigation({ dirty, busy, save }),
    { initialProps: { dirty: true, busy: true } },
  );
  act(() => requestNavigation(proceed));
  expect(result.current.pendingExit).not.toBeNull();
  expect(proceed).not.toHaveBeenCalled();
  rerender({ dirty: false, busy: false });
  expect(proceed).toHaveBeenCalledOnce();
  expect(save).not.toHaveBeenCalled();
});

test("干净页面不拦截，修改后继续编辑或放弃分别保留和执行目标动作", () => {
  const proceed = vi.fn();
  const discard = vi.fn();
  const { result, rerender } = renderHook(
    ({ dirty }) => useUnsavedNavigation({ dirty, save: vi.fn(), discard }),
    { initialProps: { dirty: false } },
  );
  expect(requestNavigation(proceed)).toBe(true);
  rerender({ dirty: true });
  act(() => expect(requestNavigation(proceed)).toBe(false));
  act(() => result.current.continueEditing());
  expect(proceed).not.toHaveBeenCalled();
  expect(discard).not.toHaveBeenCalled();
  act(() => requestNavigation(proceed));
  act(() => result.current.discardAndLeave());
  expect(discard).toHaveBeenCalledOnce();
  expect(proceed).toHaveBeenCalledOnce();
  rerender({ dirty: false });
  const unload = new Event("beforeunload", { cancelable: true });
  expect(window.dispatchEvent(unload)).toBe(true);
});

test("保存退出同步防重，失败保留目标及输入，重试成功才离开", async () => {
  let finish;
  const save = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    )
    .mockResolvedValue(true);
  const proceed = vi.fn();
  const { result } = renderHook(() => useUnsavedNavigation({ dirty: true, save }));
  act(() => requestNavigation(proceed));
  let first;
  act(() => {
    first = result.current.saveAndLeave();
    void result.current.saveAndLeave();
  });
  expect(save).toHaveBeenCalledOnce();
  act(() => result.current.discardAndLeave());
  expect(proceed).not.toHaveBeenCalled();
  await act(async () => {
    finish(false);
    await first;
  });
  expect(result.current.pendingExit).not.toBeNull();
  expect(result.current.failedSaveAttempt).toBe(1);
  expect(proceed).not.toHaveBeenCalled();
  await act(() => result.current.saveAndLeave());
  expect(proceed).toHaveBeenCalledOnce();
  expect(result.current.pendingExit).toBeNull();
});

test("刷新使用原生离页阻止，禁用保存时不会调用业务保存", async () => {
  const save = vi.fn();
  const { result } = renderHook(() =>
    useUnsavedNavigation({ dirty: true, canSave: false, save }),
  );
  const unload = new Event("beforeunload", { cancelable: true });
  expect(window.dispatchEvent(unload)).toBe(false);
  act(() => requestNavigation(vi.fn()));
  await act(() => result.current.saveAndLeave());
  expect(save).not.toHaveBeenCalled();
  expect(result.current.pendingExit).not.toBeNull();
});

test("保存失败后焦点回到保存退出，Esc只取消此次退出", async () => {
  const proceed = vi.fn();
  function Harness() {
    const guard = useUnsavedNavigation({ dirty: true, save: async () => false });
    return <UnsavedChangesDialog guard={guard} />;
  }
  render(<Harness />);
  act(() => requestNavigation(proceed));
  fireEvent.click(screen.getByRole("button", { name: "保存后离开" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存后离开" })).toHaveFocus(),
  );
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(proceed).not.toHaveBeenCalled();
});

import { StrictMode, useEffect, useRef, useState } from "react";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Modal } from "../src/components/SharedUi";
import { GlobalSearch } from "../src/app/GlobalSearch";
import { EvidenceDrawer } from "../src/features/classification-results/EvidenceDrawer";
import { renderWithServerState as render } from "./renderWithServerState";

const api = vi.hoisted(() => ({
  tasks: vi.fn(),
  datasets: vi.fn(),
  searchClassificationFeedback: vi.fn(),
  resultTaxonomy: vi.fn(),
}));
vi.mock("../src/api", () => ({ api }));
beforeEach(() => {
  vi.resetAllMocks();
  api.tasks.mockResolvedValue([
    { id: "task", title: "合成搜索任务", status: "completed" },
  ]);
  api.datasets.mockResolvedValue([]);
  api.searchClassificationFeedback.mockResolvedValue({ items: [] });
  api.resultTaxonomy.mockResolvedValue({
    labels: [{ code: "TEST", name: "合成标签", sentiment: "negative" }],
  });
});
afterEach(cleanup);

function SearchOverlay({ children }) {
  const [search, setSearch] = useState(false);
  useEffect(() => {
    const onKey = (event) => {
      if (event.ctrlKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearch(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      {children}
      {search && <GlobalSearch onClose={() => setSearch(false)} onSelect={vi.fn()} />}
    </>
  );
}

function NestedModals({ onBottomClose, initiallyOpen = false }) {
  const [inner, setInner] = useState(initiallyOpen);
  const [bottom, setBottom] = useState(true);
  return (
    bottom && (
      <Modal
        title="底层编辑"
        onClose={() => {
          onBottomClose();
          setBottom(false);
        }}
      >
        <button onClick={() => setInner(true)}>打开上层</button>
        <button>底层末项</button>
        {inner && (
          <Modal title="上层确认" onClose={() => setInner(false)}>
            <button>上层末项</button>
          </Modal>
        )}
      </Modal>
    )
  );
}

test("真实嵌套Modal只上层处理Tab和Escape，关闭恢复底层触发点", async () => {
  const closed = vi.fn();
  const user = userEvent.setup();
  render(<NestedModals onBottomClose={closed} />);
  const trigger = screen.getByRole("button", { name: "打开上层" });
  await user.click(trigger);
  const top = screen.getByRole("dialog", { name: "上层确认" });
  const first = within(top).getByRole("button", { name: "关闭" });
  expect(first).toHaveFocus();
  await user.tab({ shift: true });
  expect(within(top).getByRole("button", { name: "上层末项" })).toHaveFocus();
  await user.tab();
  expect(first).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "上层确认" })).not.toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "底层编辑" })).toBeVisible();
  expect(closed).not.toHaveBeenCalled();
  expect(trigger).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(closed).toHaveBeenCalledOnce();
});

test("同时挂载嵌套弹窗及StrictMode不让父层抢初焦点或重复关闭", async () => {
  const closed = vi.fn();
  render(
    <StrictMode>
      <NestedModals onBottomClose={closed} initiallyOpen />
    </StrictMode>,
  );
  const top = screen.getByRole("dialog", { name: "上层确认" });
  expect(within(top).getByRole("button", { name: "关闭" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("dialog", { name: "底层编辑" })).toBeVisible();
  expect(closed).not.toHaveBeenCalled();
});

test("Modal上打开真实全局搜索，Tab不落底层，IME Escape不关闭", async () => {
  const closed = vi.fn();
  const user = userEvent.setup();
  render(
    <SearchOverlay>
      <NestedModals onBottomClose={closed} />
    </SearchOverlay>,
  );
  const trigger = screen.getByRole("button", { name: "底层末项" });
  trigger.focus();
  await user.keyboard("{Control>}k{/Control}");
  const search = screen.getByRole("dialog", { name: "全局搜索" });
  const input = within(search).getByRole("textbox", { name: "全局搜索" });
  const result = await within(search).findByRole("button", { name: /合成搜索任务/ });
  expect(input).toHaveFocus();
  await user.tab({ shift: true });
  expect(result).toHaveFocus();
  await user.tab();
  expect(input).toHaveFocus();
  fireEvent.keyDown(input, { key: "Escape", isComposing: true, keyCode: 229 });
  expect(search).toBeVisible();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "全局搜索" })).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(closed).not.toHaveBeenCalled();
});

const group = {
  record: {
    id: "record",
    result_version_id: "version",
    source_record_id: "source",
    order_id: "SYNTHETIC",
    comment: "合成证据",
    classification: { semantic_units: [] },
  },
  member_count: 1,
  members: [],
};
function DrawerJourney({ onClose }) {
  const trigger = useRef(null);
  return (
    <SearchOverlay>
      <button ref={trigger}>来源记录</button>
      <EvidenceDrawer
        group={group}
        analysisContext="user_feedback"
        onClose={onClose}
        onSaved={vi.fn()}
        returnFocusRef={trigger}
      />
    </SearchOverlay>
  );
}

test("证据抽屉草稿上叠搜索，Esc先关搜索再触发原未保存确认", async () => {
  const closed = vi.fn();
  const user = userEvent.setup();
  render(<DrawerJourney onClose={closed} />);
  await user.click(screen.getByRole("button", { name: "人工修正" }));
  const add = screen.getByRole("button", { name: "补充观点" });
  await waitFor(() => expect(add).toBeEnabled());
  await user.click(add);
  expect(screen.getByLabelText("观点 1 用户观点")).toBeVisible();
  add.focus();
  await user.keyboard("{Control>}k{/Control}");
  await screen.findByRole("dialog", { name: "全局搜索" });
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "全局搜索" })).not.toBeInTheDocument();
  expect(add).toHaveFocus();
  expect(screen.queryByText("有未保存的修改，是否放弃？")).not.toBeInTheDocument();
  expect(closed).not.toHaveBeenCalled();
  await user.keyboard("{Escape}");
  expect(screen.getByText("有未保存的修改，是否放弃？")).toBeVisible();
  expect(closed).not.toHaveBeenCalled();
  expect(screen.getByLabelText("观点 1 用户观点")).toBeVisible();
});

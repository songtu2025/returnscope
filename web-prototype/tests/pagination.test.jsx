import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Pagination } from "../src/components/Pagination";
import { PAGE_SIZES } from "../src/shared/pagination";

afterEach(cleanup);

describe("Pagination", () => {
  it("保持分页结构、选项和回调契约", async () => {
    const user = userEvent.setup();
    const onPage = vi.fn();
    const onPageSize = vi.fn();
    const { container } = render(
      <Pagination
        page={2}
        pageSize={50}
        total={1234}
        totalPages={25}
        onPage={onPage}
        onPageSize={onPageSize}
      />,
    );

    expect(container.firstChild).toHaveClass("result-pagination");
    expect(container.firstChild).toHaveClass("ant-pagination");
    expect(
      screen.getByRole("navigation", { name: "分页，第 2 页，共 25 页" }),
    ).toBeVisible();
    expect(screen.getByText("共 1,234 条")).toBeVisible();
    expect(container.querySelector(".ant-pagination-item-active")).toHaveTextContent(
      "2",
    );

    const pageSize = screen.getByRole("combobox", { name: "每页数量" });
    expect(pageSize.closest(".ant-select")).toHaveTextContent("50 条/页");

    const previous = screen.getByRole("button", { name: "上一页" });
    const next = screen.getByRole("button", { name: "下一页" });
    expect(previous).toHaveAttribute("type", "button");
    expect(next).toHaveAttribute("type", "button");
    expect(previous).toBeEnabled();
    expect(next).toBeEnabled();

    await user.click(previous);
    await user.click(next);
    await user.click(pageSize);
    await user.click(await screen.findByRole("option", { name: "100 条/页" }));

    expect(onPage).toHaveBeenNthCalledWith(1, 1);
    expect(onPage).toHaveBeenNthCalledWith(2, 3);
    expect(onPageSize).toHaveBeenCalledWith(100);
    expect(PAGE_SIZES).toContain(100);
  });

  it("在首尾页保持翻页按钮禁用规则", () => {
    const props = {
      pageSize: 20,
      total: 80,
      totalPages: 4,
      onPage: vi.fn(),
      onPageSize: vi.fn(),
    };
    const { rerender } = render(<Pagination {...props} page={1} />);

    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();

    rerender(<Pagination {...props} page={4} />);

    expect(screen.getByRole("button", { name: "上一页" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });

  it("放在表单内翻页时不会提交表单", async () => {
    const user = userEvent.setup();
    const onPage = vi.fn();
    const onSubmit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Pagination
          page={2}
          pageSize={20}
          total={80}
          totalPages={4}
          onPage={onPage}
          onPageSize={vi.fn()}
        />
      </form>,
    );

    await user.click(screen.getByRole("button", { name: "下一页" }));

    expect(onPage).toHaveBeenCalledWith(3);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

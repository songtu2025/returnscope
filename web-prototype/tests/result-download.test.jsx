import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { ResultDownloadButton } from "../src/features/classification-results/ResultDownloadButton";

const { exportsMock } = vi.hoisted(() => ({
  exportsMock: { create: vi.fn(), get: vi.fn(), save: vi.fn() },
}));
vi.mock("../src/shared/api/resultExportApi", () => ({ resultExportApi: exportsMock }));

const job = { id: "job-1", status: "queued", filename: "结果.xlsx", error: "" };

function mount() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <ResultDownloadButton versionId="version-1" />
    </SWRConfig>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
  exportsMock.create.mockResolvedValue(job);
  exportsMock.get.mockResolvedValue(job);
  exportsMock.save.mockResolvedValue();
});
afterEach(cleanup);

test("提交导出后禁用重复点击，保持当前页面并自动下载完成文件", async () => {
  exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
  const location = window.location.href;
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await waitFor(() => expect(exportsMock.save).toHaveBeenCalledTimes(1));
  expect(exportsMock.create).toHaveBeenCalledWith(["version-1"]);
  expect(localStorage.getItem("result-export:version-1")).toBe("job-1");
  expect(window.location.href).toBe(location);
});

test("生成中显示局部状态，不重复提交", async () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "正在生成" }).disabled).toBe(true),
  );
  fireEvent.click(screen.getByRole("button", { name: "正在生成" }));
  expect(exportsMock.create).toHaveBeenCalledTimes(1);
});

test("刷新后恢复服务端任务，不主动重新生成", async () => {
  localStorage.setItem("result-export:version-1", "job-1");
  mount();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "正在生成" }).disabled).toBe(true),
  );
  expect(exportsMock.get).toHaveBeenCalledWith("job-1");
  expect(exportsMock.create).not.toHaveBeenCalled();
});

test("生成失败后重试同一个任务可以重新进入生成状态", async () => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockResolvedValue({
    ...job,
    status: "failed",
    error: "生成失败，请重试",
  });
  mount();
  await screen.findByRole("button", { name: "重试下载" });
  exportsMock.get.mockResolvedValue(job);
  fireEvent.click(screen.getByRole("button", { name: "重试下载" }));
  await screen.findByRole("button", { name: "正在生成" });
  expect(exportsMock.create).toHaveBeenCalledTimes(1);
});

test("缓存文件可直接获取，下载失败可再次点击且保留页面", async () => {
  exportsMock.create.mockResolvedValue({ ...job, status: "ready" });
  exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
  exportsMock.save.mockRejectedValueOnce(new Error("下载失败，请重试"));
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await screen.findByText("下载失败，请重试");
  fireEvent.click(screen.getByRole("button", { name: "重试下载" }));
  await waitFor(() => expect(exportsMock.save).toHaveBeenCalledTimes(2));
  await screen.findByRole("button", { name: "下载" });
});

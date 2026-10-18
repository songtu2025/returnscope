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
  await screen.findByRole("button", { name: "重新生成" });
  exportsMock.get.mockResolvedValue(job);
  fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
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
  expect(exportsMock.create).toHaveBeenCalledTimes(2);
});

test.each([503, 403])("状态查询失败 %s 只重新查询已有任务", async (status) => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockRejectedValueOnce(
    Object.assign(new Error("查询失败"), { status }),
  );
  mount();
  const button = await screen.findByRole("button", { name: "重新查询状态" });
  exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
  fireEvent.click(button);
  await screen.findByRole("button", { name: "下载" });
  expect(exportsMock.get).toHaveBeenCalledTimes(2);
  expect(exportsMock.get).toHaveBeenLastCalledWith("job-1");
  expect(exportsMock.create).not.toHaveBeenCalled();
  expect(exportsMock.save).not.toHaveBeenCalled();
});

test.each([404, 410])("失效任务 %s 可以重新生成并保存新任务", async (status) => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockRejectedValueOnce(Object.assign(new Error("已失效"), { status }));
  exportsMock.create.mockResolvedValue({ ...job, id: "job-new" });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "重新生成" }));
  await screen.findByRole("button", { name: "正在生成" });
  expect(exportsMock.create).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem("result-export:version-1")).toBe("job-new");
});

test("服务端未提供失败原因时仍可重新生成", async () => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockResolvedValue({ ...job, status: "failed" });
  mount();
  await screen.findByRole("button", { name: "重新生成" });
  expect(screen.getByRole("alert").textContent).toContain("导出生成失败");
});

test("提交生成失败显示重新生成", async () => {
  exportsMock.create.mockRejectedValue(new Error("生成服务暂不可用"));
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await screen.findByRole("button", { name: "重新生成" });
  expect(screen.getByRole("alert").textContent).toContain("生成服务暂不可用");
});

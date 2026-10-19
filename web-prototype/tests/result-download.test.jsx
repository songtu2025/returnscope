import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { ResultDownloadButton } from "../src/features/classification-results/ResultDownloadButton";

const { exportsMock } = vi.hoisted(() => ({
  exportsMock: { create: vi.fn(), get: vi.fn(), save: vi.fn() },
}));
vi.mock("../src/shared/api/resultExportApi", () => ({ resultExportApi: exportsMock }));

const job = {
  id: "job-1",
  status: "queued",
  filename: "结果.xlsx",
  error: "",
  expires_at: Date.now() / 1000 + 3600,
};

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
  expect(JSON.parse(localStorage.getItem("result-export:version-1"))).toEqual({
    id: "job-1",
    expires_at: job.expires_at,
  });
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
  await screen.findByRole("button", { name: "重试导出" });
  exportsMock.get.mockResolvedValue(job);
  fireEvent.click(screen.getByRole("button", { name: "重试导出" }));
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
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "重试下载" })).toBeEnabled(),
  );
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

test("旧导出缓存已清理时静默恢复下载，不主动生成；点击后保存新任务和有效期", async () => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockRejectedValueOnce(
    Object.assign(new Error("已清理"), { status: 410 }),
  );
  exportsMock.create.mockResolvedValue({ ...job, id: "job-new" });
  mount();
  const button = await screen.findByRole("button", { name: "下载" });
  await waitFor(() => expect(button).toBeEnabled());
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(localStorage.getItem("result-export:version-1")).toBeNull();
  expect(exportsMock.create).not.toHaveBeenCalled();
  exportsMock.get.mockResolvedValue(job);
  fireEvent.click(button);
  await screen.findByRole("button", { name: "正在生成" });
  expect(exportsMock.create).toHaveBeenCalledTimes(1);
  expect(JSON.parse(localStorage.getItem("result-export:version-1")).id).toBe(
    "job-new",
  );
});

test("服务端未提供失败原因时仍可重新生成", async () => {
  localStorage.setItem("result-export:version-1", "job-1");
  exportsMock.get.mockResolvedValue({ ...job, status: "failed" });
  mount();
  await screen.findByRole("button", { name: "重试导出" });
  expect(screen.getByRole("alert").textContent).toContain("导出生成失败");
});

test("提交生成失败显示重新生成", async () => {
  exportsMock.create.mockRejectedValue(new Error("生成服务暂不可用"));
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await screen.findByRole("button", { name: "重试导出" });
  expect(screen.getByRole("alert").textContent).toContain("生成服务暂不可用");
});

test("本地已过期的任务指针直接清理，不查询也不生成", () => {
  localStorage.setItem(
    "result-export:version-1",
    JSON.stringify({ ...job, expires_at: Date.now() / 1000 - 1 }),
  );
  mount();
  expect(screen.getByRole("button", { name: "下载" })).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(exportsMock.get).not.toHaveBeenCalled();
  expect(exportsMock.create).not.toHaveBeenCalled();
  expect(localStorage.getItem("result-export:version-1")).toBeNull();
});

test.each(["query", "create", "save"])(
  "%s 阶段分类结果不存在时不当作缓存过期，不自动重建",
  async (stage) => {
    const missing = Object.assign(new Error("分类结果版本不存在"), { status: 404 });
    if (stage === "query") {
      localStorage.setItem("result-export:version-1", "job-1");
      exportsMock.get.mockRejectedValue(missing);
    } else {
      exportsMock.create.mockResolvedValue({ ...job, status: "ready" });
      if (stage === "create") exportsMock.create.mockRejectedValue(missing);
      else exportsMock.save.mockRejectedValue(missing);
    }
    mount();
    if (stage !== "query")
      fireEvent.click(screen.getByRole("button", { name: "下载" }));
    expect(await screen.findByRole("button", { name: "无法下载" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("分类结果不存在，请刷新页面");
    expect(exportsMock.create).toHaveBeenCalledTimes(stage === "query" ? 0 : 1);
  },
);

test("核对后下载文件被清理，同一次点击只重新准备一次并下载", async () => {
  exportsMock.create.mockResolvedValue({ ...job, status: "ready" });
  exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
  exportsMock.save.mockRejectedValueOnce(
    Object.assign(new Error("缓存消失"), { status: 410 }),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "下载" }));
  await waitFor(() => expect(exportsMock.save).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "下载" })).toBeEnabled(),
  );
  expect(exportsMock.create).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test.each(["missing", "generation"])(
  "自动重新准备再次遇到 %s 错误时停止，不循环重试",
  async (stage) => {
    exportsMock.create.mockResolvedValue({ ...job, status: "ready" });
    exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
    exportsMock.save.mockRejectedValue(
      Object.assign(new Error("缓存已清理"), { status: 410 }),
    );
    if (stage === "generation")
      exportsMock.create
        .mockResolvedValueOnce({ ...job, status: "ready" })
        .mockRejectedValueOnce(new Error("生成服务不可用"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "下载" }));
    await screen.findByRole("alert");
    expect(exportsMock.create).toHaveBeenCalledTimes(2);
    expect(exportsMock.save).toHaveBeenCalledTimes(stage === "missing" ? 2 : 1);
  },
);

test("有效的已完成缓存仅恢复按钮，不自动下载；主动点击仍核对最新数据", async () => {
  localStorage.setItem("result-export:version-1", JSON.stringify(job));
  exportsMock.get.mockResolvedValue({ ...job, status: "ready" });
  mount();
  const button = await screen.findByRole("button", { name: "下载" });
  await waitFor(() => expect(button).toBeEnabled());
  expect(exportsMock.save).not.toHaveBeenCalled();
  expect(exportsMock.create).not.toHaveBeenCalled();
  exportsMock.create.mockResolvedValue({ ...job, id: "fresh-job", status: "ready" });
  fireEvent.click(button);
  await waitFor(() =>
    expect(exportsMock.save).toHaveBeenCalledWith(
      expect.objectContaining({ id: "fresh-job" }),
    ),
  );
});

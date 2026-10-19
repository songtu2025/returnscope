import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  control: vi.fn(),
  task: vi.fn(),
  refresh: vi.fn(),
}));
export { mocks };
vi.mock("../src/shared/api/request", async (load) => ({
  ...(await load()),
  request: mocks.request,
}));
vi.mock("../src/shared/api/taskApi", async (load) => ({
  taskApi: {
    ...(await load()).taskApi,
    controlTaskSegment: mocks.control,
    task: mocks.task,
  },
}));
vi.mock("../src/shared/serverState", async (load) => ({
  ...(await load()),
  refreshServerState: mocks.refresh,
}));

export const item = {
  id: "synthetic-segment",
  task_id: "synthetic-task",
  segment_key: "synthetic-key",
  task_revision: 3,
  task_title: "合成验收任务",
  scope: { listing: "SYNTHETIC", store: "合成站点" },
  removed_by: "合成用户",
  deleted_at: "2026-10-14T00:00:00Z",
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.request.mockResolvedValue({ items: [item], total: 1 });
  mocks.task.mockResolvedValue({
    id: item.task_id,
    revision: 3,
    segments: [{ ...item, status: "paused" }],
  });
  mocks.control.mockResolvedValue({});
  mocks.refresh.mockResolvedValue(undefined);
});
afterEach(cleanup);

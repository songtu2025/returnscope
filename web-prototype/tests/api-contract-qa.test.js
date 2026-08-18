import { afterEach, expect, test, vi } from "vitest";

import { api } from "../src/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("结果发布重试使用约定的 POST 路径和并发控制参数", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ id: "task-1", revision: 8 }),
  });
  vi.stubGlobal("fetch", fetchMock);

  await api.retrySegmentResultPublish("task-1", "segment/1", {
    expected_revision: 7,
    reason: "重新发布分类结果",
  });

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/tasks/task-1/segments/segment%2F1/retry-result-publish",
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      headers: expect.objectContaining({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        expected_revision: 7,
        reason: "重新发布分类结果",
      }),
    }),
  );
});

test("复核批次 API 使用冻结路径、服务端筛选和 revision", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ items: [], total: 0, page: 1, page_size: 20 }),
  });
  vi.stubGlobal("fetch", fetchMock);

  await api.reviewBatches({
    page: 2,
    page_size: 50,
    status: "draft",
    base_result_version_id: "version/1",
    q: "SR001",
  });
  await api.reviewBatchRecords("batch/1", {
    page: 1,
    page_size: 20,
    workflow_status: "pending",
    listing: "SR001",
    product_name: "产品名称",
    product_sku: "SKU-1",
    order_id: "ORDER-1",
  });
  await api.updateReviewBatchRecord("batch/1", "record/1", {
    expected_revision: 3,
    label_code: "FIT_TOO_SMALL",
    reason: "证据充分",
  });
  await api.publishReviewBatch("batch/1", {
    expected_revision: 4,
    reason: "复核完成",
  });

  expect(fetchMock.mock.calls[0][0]).toBe(
    "/api/review-batches?page=2&page_size=50&status=draft&base_result_version_id=version%2F1&q=SR001",
  );
  expect(fetchMock.mock.calls[1][0]).toBe(
    "/api/review-batches/batch/1/records?page=1&page_size=20&workflow_status=pending&listing=SR001&product_name=%E4%BA%A7%E5%93%81%E5%90%8D%E7%A7%B0&product_sku=SKU-1&order_id=ORDER-1",
  );
  expect(fetchMock.mock.calls[2]).toEqual([
    "/api/review-batches/batch/1/records/record/1",
    expect.objectContaining({
      method: "PATCH",
      body: JSON.stringify({
        expected_revision: 3,
        label_code: "FIT_TOO_SMALL",
        reason: "证据充分",
      }),
    }),
  ]);
  expect(fetchMock.mock.calls[3]).toEqual([
    "/api/review-batches/batch/1/publish",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ expected_revision: 4, reason: "复核完成" }),
    }),
  ]);
});

test("分析看板 API 使用冻结路径、计划哈希和服务端下钻", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({}),
  });
  vi.stubGlobal("fetch", fetchMock);

  await api.dashboardPreflight({
    result_version_ids: ["result-1"],
    filters: { store_site: "SEEKWAY:US" },
  });
  await api.createAnalysisDashboard({
    name: "退货看板",
    description: "经营复盘",
    result_version_ids: ["result-1"],
    filters: {},
    plan_hash: "plan-1",
    reason: "首次生成",
  });
  await api.createAnalysisDashboardVersion("dashboard-1", {
    expected_revision: 2,
    result_version_ids: ["result-2"],
    filters: {},
    plan_hash: "plan-2",
    reason: "更新来源",
  });
  await api.analysisDashboardDrilldown("dashboard-1", "version-2", "product_name", {
    problem: "FIT_TOO_SMALL",
    listing: "L001",
  });
  await api.analysisDashboardRecords("dashboard-1", "version-2", {
    page: 2,
    page_size: 50,
    product_name: "产品A",
    order_id: "ORDER-1",
  });

  expect(fetchMock.mock.calls[0]).toEqual([
    "/api/dashboard-plans/preflight",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        result_version_ids: ["result-1"],
        filters: { store_site: "SEEKWAY:US" },
      }),
    }),
  ]);
  expect(fetchMock.mock.calls[1][0]).toBe("/api/analysis-dashboards");
  expect(fetchMock.mock.calls[2]).toEqual([
    "/api/analysis-dashboards/dashboard-1/versions",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        expected_revision: 2,
        result_version_ids: ["result-2"],
        filters: {},
        plan_hash: "plan-2",
        reason: "更新来源",
      }),
    }),
  ]);
  expect(fetchMock.mock.calls[3][0]).toBe(
    "/api/analysis-dashboards/dashboard-1/versions/version-2/drilldown?group_by=product_name&problem=FIT_TOO_SMALL&listing=L001",
  );
  expect(fetchMock.mock.calls[4][0]).toBe(
    "/api/analysis-dashboards/dashboard-1/versions/version-2/records?page=2&page_size=50&product_name=%E4%BA%A7%E5%93%81A&order_id=ORDER-1",
  );
});

test("运营工作台、数据质量、版本引用、导入规则和审计使用冻结接口", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ items: [], total: 0, page: 1, page_size: 20 }),
  });
  vi.stubGlobal("fetch", fetchMock);

  await api.summary(5);
  await api.dataVersionReferences("returns/v2", { page: 2, page_size: 20 });
  await api.qualityPreflight("returns/v2", "products/v1");
  await api.qualityIssues({
    returns_version_id: "returns/v2",
    products_version_id: "products/v1",
    issue_type: "missing_category",
    q: "SR001",
    page: 1,
    page_size: 20,
  });
  await api.importRules();
  await api.logs({
    actor_id: "user-1",
    entity_type: "task",
    entity_id: "task-1",
    action: "update",
    date_from: "2026-08-01",
    date_to: "2026-08-12",
    page: 1,
    page_size: 20,
  });

  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/workbench/summary?limit=5",
    "/api/data-versions/returns/v2/references?page=2&page_size=20",
    "/api/data-quality/preflight?returns_version_id=returns%2Fv2&products_version_id=products%2Fv1",
    "/api/data-quality/issues?returns_version_id=returns%2Fv2&products_version_id=products%2Fv1&issue_type=missing_category&q=SR001&page=1&page_size=20",
    "/api/import-rules",
    "/api/audit-logs?actor_id=user-1&entity_type=task&entity_id=task-1&action=update&date_from=2026-08-01&date_to=2026-08-12&page=1&page_size=20",
  ]);
});

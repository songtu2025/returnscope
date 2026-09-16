import { expect, test } from "vitest";

import {
  resultRouteQuery,
  reviewBatchRouteState,
} from "../src/features/review-batches/reviewBatchRoute";

test("复核批次路由使用稳定默认值并限制分页大小", () => {
  expect(reviewBatchRouteState({})).toEqual({
    batchId: "",
    resultVersionId: "",
    status: "",
    page: 1,
    pageSize: 20,
    listing: "",
    productName: "",
    productSku: "",
    orderId: "",
    q: "",
    taskId: "",
    segmentId: "",
    returnTo: "",
  });

  expect(reviewBatchRouteState({ page: "-2", page_size: "999" })).toMatchObject({
    page: 1,
    pageSize: 20,
  });
});

test("返回分类结果时恢复来源查询并保留复核上下文", () => {
  expect(
    resultRouteQuery(
      {
        batchId: "batch-1",
        taskId: "task-1",
        segmentId: "segment-1",
        returnTo: "classification-results?quality_status=review_required&page=3",
      },
      "version-2",
      "history",
    ),
  ).toEqual({
    quality_status: "review_required",
    page: "3",
    result_version_id: "version-2",
    review_batch_id: "batch-1",
    task_id: "task-1",
    segment_id: "segment-1",
    tab: "history",
    action: "",
  });
});

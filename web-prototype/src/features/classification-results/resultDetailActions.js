import { navigateHash } from "../../app/hashRouter";

/** @typedef {import("./classificationResultDetailContracts").ResultDetailViewProps} ResultDetailViewProps */

/** @param {Pick<ResultDetailViewProps,"route"|"updateRoute"|"result"|"createDashboardFromResult"|"openOrderRecords"> & {policy:ReturnType<typeof import("./resultActionPolicy").resultActionPolicy>}} props */
export function resultDetailActions({
  route,
  updateRoute,
  result,
  createDashboardFromResult,
  openOrderRecords,
  policy,
}) {
  const runPrimaryAction = () => {
    if (policy.primary.kind === "create-dashboard") {
      createDashboardFromResult();
      return;
    }
    if (policy.primary.kind === "enter-review") {
      navigateHash("classification-results", {
        view: "reviews",
        review_batch_id: policy.primary.reviewBatchId,
        result_version_id: result.version_id,
        task_id: route.taskId || result.source_task_id,
        segment_id: route.segmentId || result.source_segment_id,
        listing: route.listing,
      });
      return;
    }
    if (policy.primary.kind === "create-review") {
      updateRoute({ tab: "history", action: "review" });
      return;
    }
    if (policy.primary.kind === "repair-source") {
      navigateHash("analysis-tasks", {
        task_id: policy.primary.taskId,
        segment_id: route.segmentId,
      });
      return;
    }
    openOrderRecords();
  };

  /** @param {string} version */
  const selectVersion = (version) =>
    updateRoute({
      version,
      tab: "history",
      recordPage: 1,
      problem: "",
      productName: "",
      productSku: "",
      orderId: "",
    });
  /** @param {string} problem */
  const selectProblem = (problem) =>
    updateRoute({
      problem,
      productName: "",
      productSku: "",
      recordPage: 1,
    });
  /** @param {string} productName */
  const selectProductName = (productName) =>
    updateRoute({ productName, productSku: "", recordPage: 1 });
  /** @param {string} productSku */
  const selectProductSku = (productSku) => updateRoute({ productSku, recordPage: 1 });
  /** @param {number} recordPage */
  const changeRecordPage = (recordPage) => updateRoute({ recordPage });
  /** @param {number} pageSize */
  const changePageSize = (pageSize) => updateRoute({ recordPage: 1, pageSize });

  return {
    runPrimaryAction,
    selectVersion,
    selectProblem,
    selectProductName,
    selectProductSku,
    changeRecordPage,
    changePageSize,
  };
}

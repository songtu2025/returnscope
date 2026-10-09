/** @typedef {import("./classificationResultDetailContracts").ResultDetailViewProps} ResultDetailViewProps */

/** @param {Pick<ResultDetailViewProps,"updateRoute"|"createDashboardFromResult">} props */
export function resultDetailActions({ updateRoute, createDashboardFromResult }) {
  const runPrimaryAction = createDashboardFromResult;

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

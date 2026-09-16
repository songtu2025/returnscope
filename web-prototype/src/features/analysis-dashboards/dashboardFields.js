/** @typedef {import("./analysisDashboardContracts").DashboardSource} DashboardSource */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */

/** @param {DashboardSource | null | undefined} source */
export function resultSourceVersionNumber(source) {
  return source?.version_no ?? source?.result_version_no;
}

/** @param {DashboardVersion | null | undefined} version */
export function dashboardVersionNumber(version) {
  return version?.version;
}

/** @param {DashboardSource | null | undefined} source */
export function productCatalogVersionLabel(source) {
  if (!source?.product_dataset_name || source?.product_version == null) {
    return "未提供产品信息版本";
  }
  return `${source.product_dataset_name} · v${source.product_version}`;
}

export function dashboardVersionId(version) {
  return version.version_id || version.id;
}

export function asItems(value) {
  return Array.isArray(value) ? value : (value?.items ?? []);
}

export function isPublishedReport(report) {
  return report.status === "completed" && Boolean(report.version_no);
}

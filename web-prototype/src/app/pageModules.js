import { lazy } from "react";

const loadWorkbenchPage = () =>
  import("../features/workbench/WorkbenchPage").then((module) => ({
    default: module.WorkbenchPage,
  }));
const WorkbenchPage = lazy(loadWorkbenchPage);
const loadTaskCreatePage = () =>
  import("../features/task-create/TaskCreatePage").then((module) => ({
    default: module.TaskCreatePage,
  }));
const TaskCreatePage = lazy(loadTaskCreatePage);
const loadTaskRuntimePage = () =>
  import("../features/task-runtime/TaskRuntimePage").then((module) => ({
    default: module.TaskRuntimePage,
  }));
const TaskRuntimePage = lazy(loadTaskRuntimePage);
const ReviewCenter = lazy(() =>
  import("../pages/ReviewCenter").then((module) => ({
    default: module.ReviewCenter,
  })),
);
const loadDataAssetsPage = () =>
  import("../features/data-management/DataAssetsPage").then((module) => ({
    default: module.DataAssetsPage,
  }));
const DataAssetsPage = lazy(loadDataAssetsPage);
const loadClassificationStandardsPage = () =>
  import("../features/classification-standards/ClassificationStandardsPage").then(
    (module) => ({ default: module.ClassificationStandardsPage }),
  );
const ClassificationStandardsPage = lazy(loadClassificationStandardsPage);
const ResultsPage = lazy(() =>
  import("../pages/ResultsPage").then((module) => ({ default: module.ResultsPage })),
);
const loadClassificationResultsPage = () =>
  import("../pages/ClassificationResultsPage").then((module) => ({
    default: module.ClassificationResultsPage,
  }));
const ClassificationResultsPage = lazy(loadClassificationResultsPage);
const loadAnalysisDashboardPage = () =>
  import("../features/analysis-dashboards/AnalysisDashboardPage").then((module) => ({
    default: module.AnalysisDashboardPage,
  }));
const AnalysisDashboardPage = lazy(loadAnalysisDashboardPage);
const loadSystemSettingsPage = () =>
  import("../features/system-settings/SystemSettingsPage").then((module) => ({
    default: module.SystemSettingsPage,
  }));
const SystemSettingsPage = lazy(loadSystemSettingsPage);

/** @type {Record<string, () => Promise<unknown>>} */
const PAGE_PRELOADERS = {
  workbench: loadWorkbenchPage,
  "data-assets": loadDataAssetsPage,
  "classification-standards": loadClassificationStandardsPage,
  "analysis-tasks": loadTaskRuntimePage,
  "classification-results": loadClassificationResultsPage,
  "analysis-dashboards": loadAnalysisDashboardPage,
  settings: loadSystemSettingsPage,
};

/** @param {string} page */
export function preloadPage(page) {
  const loader = PAGE_PRELOADERS[page];
  // 预加载只是导航加速；失败时保持当前编辑，实际打开页面再由错误边界处理。
  return loader?.().catch((error) => {
    console.warn("页面预加载失败，将在打开页面时重试。", error);
  });
}

export {
  WorkbenchPage,
  TaskCreatePage,
  TaskRuntimePage,
  ReviewCenter,
  DataAssetsPage,
  ClassificationStandardsPage,
  ResultsPage,
  ClassificationResultsPage,
  AnalysisDashboardPage,
  SystemSettingsPage,
};

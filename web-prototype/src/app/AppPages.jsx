import { Suspense } from "react";
import { PageLoadingState } from "../components/SharedUi";
import { PageErrorBoundary } from "./PageErrorBoundary";
import { LegacyResultsPage, LegacyReviewPage } from "./LegacyPages";
import {
  WorkbenchPage,
  TaskCreatePage,
  TaskRuntimePage,
  DataAssetsPage,
  ClassificationStandardsPage,
  ClassificationResultsPage,
  AnalysisDashboardPage,
  SystemSettingsPage,
} from "./pageModules";

/** @typedef {import("./navigation").AppRoute} AppRoute */
/** @typedef {import("./appContracts").CurrentUser} CurrentUser */
/** @typedef {import("./appContracts").Notify} Notify */
/** @typedef {import("./appContracts").Navigate} Navigate */

/** @param {{route: AppRoute, user: CurrentUser, notify: Notify, navigate: Navigate, refreshSystem: () => Promise<void>}} props */
export function AppPages({ route, user, notify, navigate, refreshSystem }) {
  const page = route.page;
  return (
    <PageErrorBoundary key={page}>
      <Suspense
        fallback={
          <div className="standard-page">
            <PageLoadingState label="正在加载页面…" />
          </div>
        }
      >
        {page === "workbench" && <WorkbenchPage onNavigate={navigate} />}
        {page === "task-create" && (
          <TaskCreatePage
            route={route}
            onNavigate={navigate}
            notify={notify}
            onChanged={refreshSystem}
            userId={user.id}
          />
        )}
        {page === "analysis-tasks" && (
          <TaskRuntimePage
            route={route}
            notify={notify}
            onNavigate={navigate}
            onChanged={refreshSystem}
          />
        )}
        {page === "review" && (
          <LegacyReviewPage
            route={route}
            notify={notify}
            navigate={navigate}
            refreshSystem={refreshSystem}
          />
        )}
        {page === "data-assets" && (
          <DataAssetsPage
            route={route}
            notify={notify}
            onNavigate={navigate}
            userId={user.id}
          />
        )}
        {page === "classification-standards" && (
          <ClassificationStandardsPage route={route} notify={notify} />
        )}
        {page === "legacy-results" && (
          <LegacyResultsPage route={route} notify={notify} navigate={navigate} />
        )}
        {page === "classification-results" && (
          <Suspense
            fallback={
              <div className="standard-page classification-results-page">
                <PageLoadingState label="正在加载分类结果池…" />
              </div>
            }
          >
            <ClassificationResultsPage notify={notify} route={route} userId={user.id} />
          </Suspense>
        )}
        {page === "analysis-dashboards" && (
          <AnalysisDashboardPage route={route} notify={notify} userId={user.id} />
        )}
        {page === "settings" && (
          <SystemSettingsPage route={route} notify={notify} currentUser={user} />
        )}
      </Suspense>
    </PageErrorBoundary>
  );
}

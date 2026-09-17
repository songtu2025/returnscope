import { useCallback } from "react";
import "../styles/classification-results.css";

import { AntdProvider } from "../components/AntdProvider";
import { useHashRoute } from "../app/hashRouter";
import { ClassificationResultDetail } from "../features/classification-results/ClassificationResultDetail";
import { ClassificationResultList } from "../features/classification-results/ClassificationResultList";
import {
  classificationResultRouteState,
  writeClassificationResultRoute,
} from "../features/classification-results/classificationResultRoute";
import { ReviewBatchPage } from "../features/review-batches/ReviewBatchPage";
import "../styles/review-batches.css";

/** @typedef {import("../app/navigation").AppRoute} AppRoute */
/** @typedef {import("../features/classification-results/classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @typedef {{notify: (message: string, tone?: string) => void, route?: AppRoute | null, userId: string}} ClassificationResultsPageProps */

/** @param {ClassificationResultsPageProps} props */
export function ClassificationResultsPage({ notify, route: appRoute, userId }) {
  if (!appRoute) {
    return <StandaloneClassificationResultsPage notify={notify} userId={userId} />;
  }
  return (
    <ClassificationResultsContent notify={notify} appRoute={appRoute} userId={userId} />
  );
}

/** @param {Pick<ClassificationResultsPageProps, "notify" | "userId">} props */
function StandaloneClassificationResultsPage({ notify, userId }) {
  const { route: hashRoute } = useHashRoute();
  return (
    <ClassificationResultsContent
      notify={notify}
      appRoute={hashRoute}
      userId={userId}
    />
  );
}

/** @param {{notify: ClassificationResultsPageProps["notify"], appRoute: AppRoute, userId: string}} props */
function ClassificationResultsContent({ notify, appRoute, userId }) {
  const route = classificationResultRouteState(appRoute.query);
  const updateRoute = useCallback(
    /** @param {Partial<ClassificationResultRoute>} changes */
    (changes) => writeClassificationResultRoute({ ...route, ...changes }),
    [route],
  );

  if (route.view === "reviews") {
    return <ReviewBatchPage route={appRoute} notify={notify} userId={userId} />;
  }

  return (
    <AntdProvider>
      {route.version ? (
        <ClassificationResultDetail
          route={route}
          updateRoute={updateRoute}
          notify={notify}
          userId={userId}
        />
      ) : (
        <ClassificationResultList
          route={route}
          updateRoute={updateRoute}
          notify={notify}
          userId={userId}
        />
      )}
    </AntdProvider>
  );
}

import { useCallback, useRef } from "react";
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
/** @typedef {{notify: (message: string, tone?: string) => void, route?: AppRoute | null, userId: string, returnPosition?: import("react").MutableRefObject<import("../hooks/useListReturnPosition").ListReturnPosition | null>}} ClassificationResultsPageProps */

/** @param {ClassificationResultsPageProps} props */
export function ClassificationResultsPage({
  notify,
  route: appRoute,
  userId,
  returnPosition,
}) {
  if (!appRoute) {
    return (
      <StandaloneClassificationResultsPage
        notify={notify}
        userId={userId}
        returnPosition={returnPosition}
      />
    );
  }
  return (
    <ClassificationResultsContent
      notify={notify}
      appRoute={appRoute}
      userId={userId}
      returnPosition={returnPosition}
    />
  );
}

/** @param {Pick<ClassificationResultsPageProps, "notify" | "userId" | "returnPosition">} props */
function StandaloneClassificationResultsPage({ notify, userId, returnPosition }) {
  const { route: hashRoute } = useHashRoute();
  return (
    <ClassificationResultsContent
      notify={notify}
      appRoute={hashRoute}
      userId={userId}
      returnPosition={returnPosition}
    />
  );
}

/** @param {Omit<ClassificationResultsPageProps, "route"> & {appRoute: AppRoute}} props */
function ClassificationResultsContent({ notify, appRoute, userId, returnPosition }) {
  const localReturnPosition = useRef(
    /** @type {import("../hooks/useListReturnPosition").ListReturnPosition | null} */ (
      null
    ),
  );
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
          returnPosition={returnPosition || localReturnPosition}
          route={route}
          updateRoute={updateRoute}
          notify={notify}
          userId={userId}
        />
      )}
    </AntdProvider>
  );
}

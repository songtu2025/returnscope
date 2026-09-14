import { useCallback } from "react";

import { useHashRoute } from "../app/hashRouter";
import { ClassificationResultDetail } from "../features/classification-results/ClassificationResultDetail";
import { ClassificationResultList } from "../features/classification-results/ClassificationResultList";
import {
  classificationResultRouteState,
  writeClassificationResultRoute,
} from "../features/classification-results/classificationResultRoute";
import { ReviewBatchPage } from "../features/review-batches/ReviewBatchPage";
import "../styles/review-batches.css";

export function ClassificationResultsPage({ notify, route: appRoute, userId }) {
  if (!appRoute) {
    return <StandaloneClassificationResultsPage notify={notify} userId={userId} />;
  }
  return (
    <ClassificationResultsContent notify={notify} appRoute={appRoute} userId={userId} />
  );
}

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

function ClassificationResultsContent({ notify, appRoute, userId }) {
  const route = classificationResultRouteState(appRoute.query);
  const updateRoute = useCallback(
    (changes) => writeClassificationResultRoute({ ...route, ...changes }),
    [route],
  );

  if (route.view === "reviews") {
    return <ReviewBatchPage route={appRoute} notify={notify} userId={userId} />;
  }

  return route.version ? (
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
  );
}

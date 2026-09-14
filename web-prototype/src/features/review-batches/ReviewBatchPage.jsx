import { useCallback } from "react";

import { ReviewBatchList } from "./ReviewBatchList";
import { ReviewBatchWorkspace } from "./ReviewBatchWorkspace";
import { reviewBatchRouteState, writeReviewBatchRoute } from "./reviewBatchRoute";

export function ReviewBatchPage({ route: appRoute, notify, userId }) {
  const route = reviewBatchRouteState(appRoute.query);
  const updateRoute = useCallback(
    (changes) => writeReviewBatchRoute({ ...route, ...changes }),
    [route],
  );

  return route.batchId ? (
    <ReviewBatchWorkspace
      route={route}
      updateRoute={updateRoute}
      notify={notify}
      userId={userId}
    />
  ) : (
    <ReviewBatchList route={route} updateRoute={updateRoute} />
  );
}

import { useCallback } from "react";

import { AntdProvider } from "../../components/AntdProvider";
import { ReviewBatchList } from "./ReviewBatchList";
import { ReviewBatchWorkspace } from "./ReviewBatchWorkspace";
import { reviewBatchRouteState, writeReviewBatchRoute } from "./reviewBatchRoute";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchRoute} ReviewBatchRoute */
/**
 * @param {{route: import("../../app/navigation").AppRoute, notify: (message: string, type?: "success" | "error") => void, userId: string}} props
 */

export function ReviewBatchPage({ route: appRoute, notify, userId }) {
  const route = reviewBatchRouteState(appRoute.query);
  const updateRoute = useCallback(
    /** @param {Partial<ReviewBatchRoute>} changes */
    (changes) => writeReviewBatchRoute({ ...route, ...changes }),
    [route],
  );

  return (
    <AntdProvider>
      {route.batchId ? (
        <ReviewBatchWorkspace
          route={route}
          updateRoute={updateRoute}
          notify={notify}
          userId={userId}
        />
      ) : (
        <ReviewBatchList route={route} updateRoute={updateRoute} />
      )}
    </AntdProvider>
  );
}

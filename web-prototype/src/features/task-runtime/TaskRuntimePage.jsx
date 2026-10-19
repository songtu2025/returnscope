import { TaskRecyclePage } from "./TaskRecyclePage";
import { useRef } from "react";
import { recycleViewState, recycleViewQuery } from "./useTaskRecycleView";
import { TaskMonitor } from "./TaskMonitor";
import { buildHash, navigateHash, parseHash } from "../../app/hashRouter";
import {
  classificationResultPoolReturnQuery,
  classificationResultRouteState,
} from "../classification-results/classificationResultRoute";
import "../../styles/task-flow.css";
import { productReferenceReturnQuery } from "../data-management/productReferenceRoute";

/** @typedef {import("../../app/navigation").AppRoute} AppRoute */
/** @typedef {import("../../app/navigation").Navigate} Navigate */

/**
 * @param {{route: AppRoute, userId?: string, notify: (message: string, type?: "success" | "error") => void, onNavigate: Navigate, onChanged: () => void | Promise<unknown>, returnPosition?: import("react").MutableRefObject<import("../../hooks/useListReturnPosition").ListReturnPosition | null>, listingReturnState?: import("./useSegmentBoardView").SegmentBoardReturnRef}} props
 */

export function TaskRuntimePage({
  route,
  userId,
  notify,
  onNavigate,
  onChanged,
  returnPosition,
  listingReturnState,
}) {
  const recyclePosition = useRef(
    /** @type {import("../../hooks/useListReturnPosition").ListReturnPosition | null} */ (
      null
    ),
  );
  if (route.query.view === "recycle")
    return (
      <TaskRecyclePage
        notify={notify}
        routeQuery={route.query}
        returnPosition={recyclePosition}
      />
    );
  const query = route.query;
  const productTarget = query.product_return
    ? productReferenceReturnQuery(parseHash(query.product_return))
    : null;
  const recycleTarget = query.recycle_return ? parseHash(query.recycle_return) : null;
  const onReturnRecycle =
    recycleTarget?.page === "analysis-tasks" && recycleTarget.query.view === "recycle"
      ? () =>
          navigateHash(
            "analysis-tasks",
            recycleViewQuery(recycleViewState(recycleTarget.query)),
          )
      : undefined;
  const resultPoolTarget = query.result_pool_return
    ? parseHash(query.result_pool_return)
    : null;
  const resultPoolState =
    resultPoolTarget?.page === "classification-results"
      ? classificationResultRouteState(resultPoolTarget.query)
      : null;
  const onReturnResultPool =
    resultPoolState && !resultPoolState.version && resultPoolState.view === "results"
      ? () =>
          navigateHash(
            "classification-results",
            classificationResultPoolReturnQuery(resultPoolState),
          )
      : undefined;
  const filter =
    query.status === "active" ||
    query.status === "finished" ||
    query.status === "archived"
      ? query.status
      : "all";
  const sort =
    query.sort === "created_desc" || query.sort === "progress_desc"
      ? query.sort
      : "updated_desc";
  const listState = {
    filter,
    query: query.q || "",
    owner: query.owner || "all",
    ...(query.scope === "mine" ? { ownerId: userId || "" } : {}),
    sort,
    attentionOnly: query.attention === "1",
  };

  /** @param {Partial<typeof listState>} changes */
  const updateListState = (changes) => {
    const next = { ...listState, ...changes };
    navigateHash(
      "analysis-tasks",
      {
        ...query,
        status: next.filter === "all" ? "" : next.filter,
        q: next.query,
        owner: next.owner === "all" ? "" : next.owner,
        scope: next.ownerId === undefined ? "" : "mine",
        sort: next.sort === "updated_desc" ? "" : next.sort,
        attention: next.attentionOnly ? "1" : "",
      },
      { replace: true },
    );
  };

  /** @param {string | null} taskId */
  const focusTask = (taskId) => {
    navigateHash("analysis-tasks", {
      ...query,
      task_id: taskId,
      segment_id: taskId ? query.segment_id : "",
    });
  };

  return (
    <TaskMonitor
      userId={userId}
      notify={notify}
      onNavigate={onNavigate}
      onChanged={onChanged}
      focusId={route.query.task_id || route.query.task || null}
      focusSegmentId={route.query.segment_id || null}
      listState={listState}
      onListStateChange={updateListState}
      onTaskFocus={focusTask}
      taskReturn={buildHash("analysis-tasks", query)}
      returnPosition={returnPosition}
      listingReturnState={listingReturnState}
      onReturnResultPool={onReturnResultPool}
      onReturnRecycle={onReturnRecycle}
      onReturnProducts={
        productTarget ? () => navigateHash("data-assets", productTarget) : undefined
      }
    />
  );
}

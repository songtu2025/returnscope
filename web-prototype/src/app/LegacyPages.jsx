import { Suspense } from "react";
import { InlineLoading } from "../components/SharedUi";
import { ResultsPage, ReviewCenter } from "./pageModules";

/** @typedef {import("./navigation").AppRoute} AppRoute */
/** @typedef {import("./appContracts").Notify} Notify */
/** @typedef {import("./appContracts").Navigate} Navigate */

/** @param {{route: AppRoute, notify: Notify, navigate: Navigate, refreshSystem: () => Promise<void>}} props */
export function LegacyReviewPage({ route, notify, navigate, refreshSystem }) {
  return (
    <>
      <div className="legacy-review-notice" role="status">
        <div>
          <b>旧版单记录复核</b>
          <span>仅用于历史任务，与新版复核批次和派生版本相互独立。</span>
        </div>
        <button className="secondary-button" onClick={() => navigate("review-center")}>
          进入分类结果复核记录
        </button>
      </div>
      <ReviewCenter
        notify={notify}
        onChanged={refreshSystem}
        focus={
          route.query.review
            ? {
                kind: "review",
                id: route.query.review,
                status: route.query.status,
              }
            : null
        }
      />
    </>
  );
}

/** @param {{route: AppRoute, notify: Notify, navigate: Navigate}} props */
export function LegacyResultsPage({ route, notify, navigate }) {
  return (
    <Suspense fallback={<InlineLoading label="正在加载旧版任务分析…" />}>
      <div className="legacy-results-notice" role="status">
        <div>
          <b>旧版任务分析</b>
          <span>此页面仅用于兼容历史任务，不是新版分析看板。</span>
        </div>
        <div className="legacy-results-actions">
          <button
            className="secondary-button"
            onClick={() => navigate("analysis-dashboards")}
          >
            进入新版分析看板
          </button>
          <button
            className="secondary-button"
            onClick={() => navigate("classification-results")}
          >
            查看分类结果
          </button>
        </div>
      </div>
      <ResultsPage
        notify={notify}
        onNavigate={navigate}
        focus={
          route.query.task_id
            ? {
                kind: "result",
                id: route.query.task_id,
                listing: route.query.listing,
              }
            : null
        }
      />
    </Suspense>
  );
}

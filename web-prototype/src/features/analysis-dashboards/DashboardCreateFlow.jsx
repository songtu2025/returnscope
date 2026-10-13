import { dashboardCreationStage } from "./dashboardCreatePolicy";
import { ArrowLeft } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { DashboardPlanSources } from "./DashboardPlanSources";
import { DashboardCreateConfirmation } from "./DashboardCreateConfirmation";
import { DashboardConflictChoices } from "./DashboardConflictChoices";
import { useDashboardCreation } from "./useDashboardCreation";
import { useDashboardInsightCreation } from "./useDashboardInsightCreation";
import { DashboardInsightConfirmation } from "./DashboardInsightConfirmation";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateProps} DashboardCreateProps */

/** @param {DashboardCreateProps} props */
export function DashboardCreateFlow(props) {
  const context = { ...props, ...useDashboardCreation(props) };
  const { route, selection, state, resultVersionIds, runPreflight } = context;
  const isInsightCreation = selection?.intent === "insight";
  const insight = useDashboardInsightCreation({ ...context, isInsightCreation });

  const stage = dashboardCreationStage(state, route, selection, resultVersionIds);
  if (!stage.hasSelection) {
    return (
      <div className="standard-page analysis-dashboard-page">
        <PageHeading title="还没有选择分类结果" />
        <section className="dashboard-create-empty">
          <button
            className="primary-button"
            onClick={() => navigateHash("classification-results")}
          >
            选择分类结果
          </button>
        </section>
      </div>
    );
  }
  return (
    <div className="standard-page analysis-dashboard-page dashboard-create-page">
      <button
        className="text-button result-back-button page-loading-navigation"
        disabled={context.submitting || insight.insightState.submitting}
        onClick={() =>
          navigateHash("classification-results", {
            ...selection?.result_pool_query,
            selection_token: route.selectionToken,
          })
        }
      >
        <ArrowLeft size={17} /> 返回选择分类结果
      </button>
      <PageHeading title={isInsightCreation ? "生成 AI 洞察" : "创建分析看板"} />

      {state.loading && !state.plan && (
        <InlineLoading scope="page" label="正在检查分类结果与 Listing 冲突…" />
      )}
      {state.error && (
        <section className="dashboard-error" role="alert">
          <b>执行计划检查失败</b>
          <span>{state.error}</span>
          <button
            className="secondary-button"
            onClick={() => runPreflight(resultVersionIds)}
          >
            重新检查
          </button>
        </section>
      )}

      {stage.showConflicts && <DashboardConflictChoices {...context} />}

      {stage.showConfirmation && !isInsightCreation && (
        <section className="dashboard-confirm-page">
          <DashboardPlanSources {...context}>
            <DashboardCreateConfirmation {...context} />
          </DashboardPlanSources>
        </section>
      )}
      {stage.showConfirmation && isInsightCreation && (
        <>
          <DashboardPlanSources {...context} showQualityScope={false} />
          <DashboardInsightConfirmation {...context} {...insight} />
        </>
      )}
    </div>
  );
}

import { dashboardCreationStage } from "./dashboardCreatePolicy";
import { ArrowLeft } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { DashboardPlanSources } from "./DashboardPlanSources";
import { DashboardCreateConfirmation } from "./DashboardCreateConfirmation";
import { DashboardConflictChoices } from "./DashboardConflictChoices";
import { useDashboardCreation } from "./useDashboardCreation";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateRoute} DashboardCreateRoute */
/** @typedef {import("./dashboardCreateContracts").DashboardCreateProps} DashboardCreateProps */

/** @param {DashboardCreateProps} props */
export function DashboardCreateFlow(props) {
  const context = { ...props, ...useDashboardCreation(props) };
  const { route, selection, state, resultVersionIds, runPreflight, isVersionCreation } =
    context;

  const stage = dashboardCreationStage(state, route, selection, resultVersionIds);
  if (!stage.hasSelection) {
    return (
      <div className="standard-page analysis-dashboard-page">
        <PageHeading
          eyebrow="生成分析看板"
          title="还没有选择分类结果"
          description="选择内容只保存在当前账号的本次浏览器会话中。"
        />
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
        className="text-button result-back-button"
        onClick={() =>
          navigateHash("classification-results", {
            selection_token: route.selectionToken,
          })
        }
      >
        <ArrowLeft size={17} /> 返回选择分类结果
      </button>
      <PageHeading
        eyebrow={isVersionCreation ? "创建看板新版本" : "生成不可变看板数据集"}
        title={isVersionCreation ? "基于新分类结果创建版本" : "创建分析看板"}
      />
      <DashboardCreateSteps step={route.step} />

      {state.loading && <InlineLoading label="正在检查分类结果与 Listing 冲突…" />}
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

      {stage.showConfirmation && (
        <section className="dashboard-confirm-page">
          <DashboardPlanSources {...context} />
          <DashboardCreateConfirmation {...context} />
        </section>
      )}
    </div>
  );
}

/** @param {{step: DashboardCreateRoute["step"]}} props */
function DashboardCreateSteps({ step }) {
  const active = step === "conflicts" ? 2 : step === "confirm" ? 3 : 1;
  return (
    <ol className="dashboard-create-steps" aria-label="看板生成步骤">
      {["选择分类结果", "解决版本冲突", "确认并生成"].map((label, index) => (
        <li key={label} className={active >= index + 1 ? "active" : ""}>
          <span>{index + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}

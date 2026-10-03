import { hasDashboardCreationReason } from "./dashboardCreatePolicy";
import { GitBranch } from "@phosphor-icons/react";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext} context */
export function DashboardCreateConfirmation(context) {
  const {
    state,
    form,
    setForm,
    submitting,
    confirmationMessage,
    resultVersionIds,
    blockers,
    currentSources,
    summary,
    isVersionCreation,
    submit,
  } = context;
  return (
    <aside className="dashboard-confirm-aside">
      <DashboardPlanStats
        resultVersionIds={resultVersionIds}
        currentSources={currentSources}
        summary={summary}
      />
      {summary.total_record_count != null &&
        Number(summary.total_record_count) !== Number(summary.record_count) && (
          <DashboardCoverageNote summary={summary} />
        )}
      {!isVersionCreation && (
        <>
          <label>
            看板名称
            <input
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="输入看板名称"
            />
          </label>
          <label>
            看板说明
            <textarea
              rows={3}
              value={form.description}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
              placeholder="可选：说明使用场景"
            />
          </label>
        </>
      )}
      <label>
        {isVersionCreation ? "版本原因" : "生成原因"}
        <textarea
          rows={3}
          required
          value={form.reason}
          onChange={(event) => setForm({ ...form, reason: event.target.value })}
          placeholder="必填：说明为什么生成本次看板数据集"
        />
      </label>
      <div className="dashboard-lineage-note">
        <GitBranch size={19} />
        <span>
          {isVersionCreation
            ? "新版本会保留旧版本，历史看板不会自动漂移。"
            : "生成后固化数据来源，后续分类结果变化不会影响当前版本。"}
        </span>
      </div>
      {confirmationMessage && (
        <p className="dashboard-form-error" role="alert">
          {confirmationMessage}
        </p>
      )}
      <DashboardCreateSubmit
        state={state}
        form={form}
        submitting={submitting}
        blockers={blockers}
        isVersionCreation={isVersionCreation}
        submit={submit}
      />
    </aside>
  );
}

/** @param {Pick<Parameters<typeof DashboardCreateConfirmation>[0], "resultVersionIds" | "currentSources" | "summary" >} props */
function DashboardPlanStats({ resultVersionIds, currentSources, summary }) {
  return (
    <div className="dashboard-plan-stats">
      <span>
        结果版本
        <b>{summary.source_count ?? resultVersionIds.length}</b>
      </span>
      <span>
        Listing
        <b>{summary.listing_count ?? currentSources.length}</b>
      </span>
      <span>
        {summary.counting_basis === "feedback_group" ? "反馈组" : "记录"}
        <b>
          {summary.record_count == null
            ? "暂无统计"
            : Number(summary.record_count).toLocaleString()}
        </b>
      </span>
    </div>
  );
}
/** @param {Pick<Parameters<typeof DashboardCreateConfirmation>[0], "summary" >} props */
function DashboardCoverageNote({ summary }) {
  return (
    <div className="dashboard-coverage-note" role="status">
      <b>
        纳入 {Number(summary.record_count || 0).toLocaleString()} /{" "}
        {Number(summary.total_record_count || 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条记录"}
      </b>
      <span>
        待复核 {Number(summary.pending_review_record_count || 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}
        ；已排除 {Number(summary.excluded_record_count || 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}。
      </span>
    </div>
  );
}
/** @param {Pick<Parameters<typeof DashboardCreateConfirmation>[0], "state" | "form" | "submitting" | "blockers" | "isVersionCreation" | "submit" >} props */
function DashboardCreateSubmit({
  state,
  form,
  submitting,
  blockers,
  isVersionCreation,
  submit,
}) {
  return (
    <button
      className="primary-button dashboard-submit-button"
      disabled={
        submitting ||
        blockers.length > 0 ||
        state.plan?.ready !== true ||
        !hasDashboardCreationReason(form, isVersionCreation) ||
        !state.plan?.plan_hash
      }
      onClick={submit}
    >
      {submitting
        ? "正在生成…"
        : isVersionCreation
          ? "确认生成新版本"
          : "确认生成分析看板"}
    </button>
  );
}

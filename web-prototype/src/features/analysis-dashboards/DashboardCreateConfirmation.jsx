import { isDashboardCreationFormValid } from "./dashboardCreatePolicy";
import { GitBranch } from "@phosphor-icons/react";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext} context */
export function DashboardCreateConfirmation(context) {
  const {
    state,
    form,
    setForm,
    submitting,
    confirmationMessage,
    blockers,
    isVersionCreation,
    submit,
  } = context;
  return (
    <div
      className={
        isVersionCreation
          ? "dashboard-confirm-form"
          : "dashboard-confirm-form dashboard-confirm-form-inline"
      }
    >
      {!isVersionCreation && (
        <label>
          看板名称
          <input
            required
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="输入看板名称"
          />
        </label>
      )}
      {isVersionCreation && (
        <label>
          版本原因
          <textarea
            rows={3}
            required
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
            placeholder="必填：说明为什么生成本次看板数据集"
          />
        </label>
      )}
      <footer className="dashboard-confirm-actions">
        {isVersionCreation && (
          <div className="dashboard-lineage-note">
            <GitBranch size={19} />
            <span>新版本会保留旧版本，历史看板不会自动漂移。</span>
          </div>
        )}
        <DashboardCreateSubmit
          state={state}
          form={form}
          submitting={submitting}
          blockers={blockers}
          isVersionCreation={isVersionCreation}
          submit={submit}
        />
      </footer>
      {confirmationMessage && (
        <p className="dashboard-form-error" role="alert">
          {confirmationMessage}
        </p>
      )}
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
        state.loading ||
        Boolean(state.error) ||
        blockers.length > 0 ||
        state.plan?.ready !== true ||
        !isDashboardCreationFormValid(form, isVersionCreation) ||
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

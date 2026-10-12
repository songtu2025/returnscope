import { isDashboardCreationFormValid } from "./dashboardCreatePolicy";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext} context */
export function DashboardCreateConfirmation(context) {
  const { state, form, setForm, submitting, confirmationMessage, blockers, submit } =
    context;
  return (
    <div className="dashboard-confirm-form dashboard-confirm-form-inline">
      <label>
        看板名称
        <input
          required
          value={form.name}
          onChange={(event) => setForm({ name: event.target.value })}
          placeholder="输入看板名称"
        />
      </label>
      <footer className="dashboard-confirm-actions">
        <button
          className="primary-button dashboard-submit-button"
          disabled={
            submitting ||
            state.loading ||
            Boolean(state.error) ||
            blockers.length > 0 ||
            state.plan?.ready !== true ||
            !isDashboardCreationFormValid(form) ||
            !state.plan?.plan_hash
          }
          onClick={submit}
        >
          {submitting ? "正在生成…" : "确认生成分析看板"}
        </button>
      </footer>
      {confirmationMessage && (
        <p className="dashboard-form-error" role="alert">
          {confirmationMessage}
        </p>
      )}
    </div>
  );
}

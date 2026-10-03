import { CaretRight, WarningCircle } from "@phosphor-icons/react";
import { formatTime } from "../../lib/presentation";
import { resultSourceVersionNumber } from "./dashboardFields";
import { itemVersionId, conflictId, conflictCandidates } from "./dashboardCreatePolicy";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext} context */
export function DashboardConflictChoices(context) {
  const {
    selection,
    state,
    choices,
    setChoices,
    confirmationMessage,
    conflicts,
    resolveConflicts,
  } = context;
  return (
    <section className="dashboard-conflict-page">
      <header>
        <div>
          <WarningCircle size={24} />
          <span>
            <b>同一 Listing 选择了多个结果版本</b>
            <small>系统不会自动取最新版，请逐组确认要用于看板的数据。</small>
          </span>
        </div>
      </header>
      <div className="dashboard-conflict-list">
        {conflicts.map((conflict, index) => {
          const id = conflictId(conflict, index);
          return (
            <fieldset key={id}>
              <legend>
                {conflict.store_site || "未提供店铺/站点"} ·{" "}
                {conflict.listing || "未提供 Listing"}
              </legend>
              {conflictCandidates(conflict, selection, state.plan?.sources).map(
                (candidate) => {
                  const versionId = itemVersionId(candidate);
                  const hasProductVersion =
                    candidate.product_dataset_name && candidate.product_version != null;
                  return (
                    <label key={versionId}>
                      <input
                        type="radio"
                        name={id}
                        value={versionId}
                        checked={choices[id] === versionId}
                        onChange={() => setChoices({ ...choices, [id]: versionId })}
                      />
                      <span>
                        <b>结果 v{resultSourceVersionNumber(candidate) ?? "-"}</b>
                        <small>
                          {hasProductVersion
                            ? `产品信息：${candidate.product_dataset_name} · v${candidate.product_version}`
                            : "产品信息版本未记录"}
                        </small>
                        <small>
                          {Number(candidate.record_count || 0).toLocaleString()} 条记录
                          · {formatTime(candidate.published_at)}
                        </small>
                      </span>
                    </label>
                  );
                },
              )}
            </fieldset>
          );
        })}
      </div>
      {confirmationMessage && (
        <p className="dashboard-form-error">{confirmationMessage}</p>
      )}
      <footer>
        <button className="primary-button" onClick={resolveConflicts}>
          确认冲突选择 <CaretRight size={17} />
        </button>
      </footer>
    </section>
  );
}

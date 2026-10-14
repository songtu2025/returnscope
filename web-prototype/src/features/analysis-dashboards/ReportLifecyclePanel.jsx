import { useState } from "react";
import { DeliveryLifecycleControls } from "../../components/DeliveryLifecycleControls";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { errorMessage } from "./dashboardRequestErrors";

/** @param {{dashboardId: string, versionId: string, report: import("./analysisDashboardContracts").InsightReport | null, onChanged: () => void | Promise<void>}} props */
export function ReportLifecyclePanel({ dashboardId, versionId, report, onChanged }) {
  const [removed, setRemoved] = useState(
    /** @type {import("./analysisDashboardContracts").InsightReport[] | null} */ (null),
  );
  const [error, setError] = useState("");
  const load = async () => {
    try {
      const values = await dashboardApi.deletedInsightReports(dashboardId, versionId);
      setRemoved(
        values.filter(
          (/** @type {import("./analysisDashboardContracts").InsightReport} */ item) =>
            item.deleted_at,
        ),
      );
      setError("");
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };
  return (
    <section className="result-action-guidance">
      {report && !["queued", "running"].includes(report.status) && (
        <DeliveryLifecycleControls
          kind="report"
          id={report.id}
          name={`报告 ${report.version_no ?? report.attempt_no}`}
          revision={report.revision ?? 1}
          onChanged={onChanged}
        />
      )}
      <button
        className="secondary-button"
        onClick={() => (removed ? setRemoved(null) : void load())}
      >
        {removed ? "关闭已删除报告" : "已删除报告"}
      </button>
      {removed?.map((item) => (
        <div key={item.id}>
          报告 {item.version_no ?? item.attempt_no}
          <DeliveryLifecycleControls
            kind="report"
            id={item.id}
            name="报告"
            revision={item.revision ?? 1}
            deleted
            onChanged={async () => {
              await load();
              await onChanged();
            }}
          />
        </div>
      ))}
      {removed?.length === 0 && <span>没有已删除报告</span>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

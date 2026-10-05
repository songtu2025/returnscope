import { useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { errorMessage } from "./dashboardRequestErrors";
import { useDashboardReportGeneration } from "./useDashboardReportGeneration";

/** @typedef {import("./dashboardDetailContracts").ReportDecision} ReportDecision */
/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps & Pick<ReturnType<typeof import("./useDashboardReports").useDashboardReports>, "setReports" | "selectedReport">} props */
export function useDashboardReportActions({
  route,
  updateRoute,
  notify,
  setReports,
  selectedReport,
}) {
  const { decisionState, setIssueDecision } = useDashboardIssueDecision({
    notify,
    setReports,
    selectedReport,
  });
  const {
    generationOpen,
    setGenerationOpen,
    generationState,
    generationForm,
    setGenerationForm,
    openReportGeneration,
    submitReportGeneration,
  } = useDashboardReportGeneration({ route, updateRoute, notify, setReports });
  const retryReport = async () => {
    if (!selectedReport) return;
    try {
      /** @type {InsightReport} */
      const report = await dashboardApi.retryInsightReport(selectedReport.id);
      setReports((current) => ({
        ...current,
        items: [report, ...current.items],
      }));
      updateRoute({ reportId: report.id, issueId: "" }, { replace: true });
      notify?.("新的生成尝试已加入队列，原失败记录已保留");
    } catch (error) {
      setReports((current) => ({ ...current, error: errorMessage(error) }));
    }
  };
  return {
    decisionState,
    generationOpen,
    setGenerationOpen,
    generationState,
    generationForm,
    setGenerationForm,
    openReportGeneration,
    submitReportGeneration,
    retryReport,
    setIssueDecision,
  };
}

/** @param {Pick<Parameters<typeof useDashboardReportActions>[0], "notify" | "setReports" | "selectedReport">} props */
function useDashboardIssueDecision({ notify, setReports, selectedReport }) {
  const [decisionState, setDecisionState] = useState({
    issueId: "",
    loading: false,
    error: "",
  });
  /**
   * @param {string} issueId
   * @param {string} status
   */
  const setIssueDecision = async (issueId, status) => {
    if (!selectedReport) return;
    setDecisionState({ issueId, loading: true, error: "" });
    try {
      /** @type {ReportDecision} */
      const decision = await dashboardApi.setInsightReportIssueDecision(
        selectedReport.id,
        issueId,
        status,
      );
      setReports((current) => ({
        ...current,
        items: current.items.map((item) => {
          if (item.id !== selectedReport.id) return item;
          const decisions = (item.decisions ?? []).filter(
            (value) => value.issue_id !== issueId,
          );
          return { ...item, decisions: [decision, ...decisions] };
        }),
      }));
      setDecisionState({ issueId: "", loading: false, error: "" });
      notify?.("问题状态已更新");
    } catch (error) {
      setDecisionState({ issueId, loading: false, error: errorMessage(error) });
    }
  };
  return { decisionState, setIssueDecision };
}

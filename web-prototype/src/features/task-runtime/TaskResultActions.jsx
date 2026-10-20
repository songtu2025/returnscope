import { ChartBar, Sparkle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { buildHash, navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { publishedTaskResults } from "./taskSegmentPolicy";

/** @param {{task: import("./taskRuntimeContracts").AnalysisTask, userId: string, taskReturn?: string, disabled?: boolean}} props */
export function TaskResultActions({ task, userId, taskReturn, disabled }) {
  const selected = publishedTaskResults(task).map((segment) =>
    selectionItem({
      result_version_id: segment.result_version_id,
      version: segment.result_version,
      store_site: segment.scope?.store,
      listing: segment.scope?.listing,
      quality_status: segment.result_quality_status,
      record_count: segment.record_count,
      unit_count: segment.unique_comments,
    }),
  );
  if (!selected.length) return null;
  /** @param {"dashboard" | "insight"} intent */
  const openCreation = (intent) => {
    const token = createDashboardSelection(userId, {
      selected,
      intent,
      task_return: taskReturn || buildHash("analysis-tasks", { task_id: task.id }),
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };
  return (
    <>
      <Button
        disabled={disabled}
        className="secondary-button"
        icon={<ChartBar size={17} />}
        title={`使用本任务 ${selected.length} 个有效已发布结果，下一步核对范围`}
        onClick={() => openCreation("dashboard")}
      >
        用本任务结果创建看板
      </Button>
      <Button
        disabled={disabled}
        className="secondary-button"
        icon={<Sparkle size={17} />}
        title={`使用本任务 ${selected.length} 个有效已发布结果，下一步核对范围`}
        onClick={() => openCreation("insight")}
      >
        用本任务结果生成 AI 洞察（{selected.length}）
      </Button>
    </>
  );
}

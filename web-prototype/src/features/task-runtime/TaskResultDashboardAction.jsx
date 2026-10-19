import { ChartBar } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { buildHash, navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { isPublishedResult } from "./taskSegmentPolicy";

/** @param {{task: import("./taskRuntimeContracts").AnalysisTask, userId: string, taskReturn?: string, disabled?: boolean}} props */
export function TaskResultDashboardAction({ task, userId, taskReturn, disabled }) {
  const segments = (task.segments ?? []).filter(
    (segment) =>
      !segment.deleted_at && segment.result_version_id && isPublishedResult(segment),
  );
  const selected = [
    ...new Map(
      segments.map((segment) => [
        segment.result_version_id,
        selectionItem({
          result_version_id: segment.result_version_id,
          version: segment.result_version,
          store_site: segment.scope?.store,
          listing: segment.scope?.listing,
          quality_status: segment.result_quality_status,
          record_count: segment.record_count,
          unit_count: segment.unique_comments,
        }),
      ]),
    ).values(),
  ];
  if (!selected.length) return null;
  return (
    <Button
      disabled={disabled}
      className="secondary-button"
      icon={<ChartBar size={17} />}
      title={`使用本任务 ${selected.length} 个有效已发布结果，下一步核对范围`}
      onClick={() => {
        const token = createDashboardSelection(userId, {
          selected,
          task_return: taskReturn || buildHash("analysis-tasks", { task_id: task.id }),
        });
        navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
      }}
    >
      用本任务结果创建看板
    </Button>
  );
}

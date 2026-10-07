import { ArrowRight, ListChecks } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { ACTION_LABELS, nextActionLabel, openTarget } from "./workbenchPolicy";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchAction} WorkbenchAction */
/** @typedef {import("./workbenchPolicy").WorkbenchViewState} WorkbenchViewState */

/** @param {{actions: WorkbenchAction[], state: WorkbenchViewState, onNavigate: (destination: string) => void}} props */
export function WorkbenchActions({ actions, state, onNavigate }) {
  const { isLoading, hasData, message } = state;
  return (
    <section className="content-card workbench-card workbench-action-card">
      <header>
        <div>
          <b>待处理与后台进度</b>
          <span>阻断、失败、需复核、暂停和报告生成进度，最多显示 5 项</span>
        </div>
        <button className="text-button" onClick={() => onNavigate("analysis-tasks")}>
          查看分析任务 <ArrowRight size={15} />
        </button>
      </header>
      {isLoading && !hasData ? (
        <InlineLoading label="正在读取待行动事项…" />
      ) : message && !hasData ? null : actions.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="当前没有待处理事项或后台任务"
          description="阻断、失败、需复核、暂停和报告生成进度会出现在这里。"
        />
      ) : (
        <WorkbenchActionItems actions={actions} />
      )}
    </section>
  );
}

/** @param {{actions: WorkbenchAction[]}} props */
function WorkbenchActionItems({ actions }) {
  return (
    <div className="workbench-action-list">
      {actions.map((action) => (
        <button
          key={`${action.object_type}-${action.object_id}`}
          onClick={() => openTarget(action.target)}
        >
          <span className={`workbench-action-type ${action.type}`}>
            {ACTION_LABELS[action.type] ?? action.type}
          </span>
          <span className="workbench-action-copy">
            <b>{action.title}</b>
            <small>{action.reason || "未提供原因"}</small>
            <em>
              {action.actor?.name || "未提供操作人"} · {formatTime(action.updated_at)}
            </em>
          </span>
          <span className="workbench-action-status">
            {nextActionLabel(action)}
            <ArrowRight size={15} />
          </span>
        </button>
      ))}
    </div>
  );
}

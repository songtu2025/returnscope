import { ArrowRight, ChartBar, Plus } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { OUTPUT_LABELS, openTarget } from "./workbenchPolicy";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchOutput} WorkbenchOutput */
/** @typedef {import("./workbenchPolicy").WorkbenchViewState} WorkbenchViewState */

/** @param {{recentOutputs: WorkbenchOutput[], state: WorkbenchViewState, onNavigate: (destination: string) => void}} props */
export function WorkbenchOutputs({ recentOutputs, state, onNavigate }) {
  const { isLoading, hasData, message } = state;
  return (
    <section className="content-card workbench-card workbench-output-card">
      <header>
        <div>
          <b>最近产出</b>
          <span>分类结果、分析看板和已发布 AI 洞察报告</span>
        </div>
        <button
          className="text-button"
          onClick={() => onNavigate("classification-results")}
        >
          查看分类结果 <ArrowRight size={15} />
        </button>
      </header>
      {isLoading && !hasData ? (
        <InlineLoading label="正在读取最近产出…" />
      ) : message && !hasData ? null : recentOutputs.length === 0 ? (
        <EmptyState
          icon={ChartBar}
          title="还没有可查看的产出"
          description="完成分析并发布分类结果后，最新产出会集中显示在这里。"
          action={
            <button
              className="secondary-button"
              onClick={() => onNavigate("task-create")}
            >
              <Plus size={16} />
              创建分析任务
            </button>
          }
        />
      ) : (
        <WorkbenchOutputItems recentOutputs={recentOutputs} />
      )}
    </section>
  );
}

/** @param {{recentOutputs: WorkbenchOutput[]}} props */
function WorkbenchOutputItems({ recentOutputs }) {
  return (
    <div className="workbench-output-list">
      {recentOutputs.map((output) => (
        <button
          key={`${output.type}-${output.version_id}`}
          onClick={() => openTarget(output.target)}
        >
          <span>
            <em>{OUTPUT_LABELS[output.type] ?? output.type}</em>
            <b>{output.title}</b>
            <small>{formatTime(output.updated_at)}</small>
          </span>
          <span>
            v{output.version_no ?? "-"}
            <ArrowRight size={15} />
          </span>
        </button>
      ))}
    </div>
  );
}

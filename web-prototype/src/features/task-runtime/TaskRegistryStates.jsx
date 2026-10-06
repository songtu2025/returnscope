import { PlayCircle, WarningCircle } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";

/** @typedef {import("./TaskRegistry").TaskRegistryProps} TaskRegistryProps */
/**
 * @typedef {Pick<TaskRegistryProps, "tasks" | "loading" | "error" | "hasData" | "onReload" | "onCreate"> & {deferredQuery: string, owner: string, filter: string, visibleCount: number}} TaskRegistryStatesProps
 */

/** @param {Pick<TaskRegistryStatesProps, "error" | "hasData" | "onReload">} props */
function RegistryError({ error, hasData, onReload }) {
  return (
    <div className="task-list-error" role="alert">
      <EmptyState
        icon={WarningCircle}
        title={hasData ? "任务列表更新失败，当前显示上一次数据" : "任务列表读取失败"}
        description={error}
        action={
          <button className="secondary-button" onClick={onReload}>
            重新加载
          </button>
        }
      />
    </div>
  );
}

/** @param {Pick<TaskRegistryStatesProps, "tasks" | "deferredQuery" | "owner" | "filter" | "onCreate">} props */
function RegistryEmpty({ tasks, deferredQuery, owner, filter, onCreate }) {
  return (
    <EmptyState
      icon={PlayCircle}
      title={deferredQuery || owner !== "all" ? "没有匹配任务" : "暂无任务"}
      description={
        deferredQuery || owner !== "all"
          ? "请调整搜索词或筛选条件。"
          : filter === "active"
            ? "新任务开始后，会在这里展示实时进度。"
            : "当前分组中没有任务记录。"
      }
      action={
        tasks.length === 0 ? (
          <button className="primary-button" onClick={onCreate}>
            创建分析任务
          </button>
        ) : null
      }
    />
  );
}

/** @param {TaskRegistryStatesProps} props */
export function TaskRegistryStates(props) {
  const { loading, error, hasData, visibleCount } = props;
  return (
    <>
      {loading && <InlineLoading label="读取任务…" />}
      {!loading && error && (
        <RegistryError error={error} hasData={hasData} onReload={props.onReload} />
      )}
      {!loading && (!error || hasData) && visibleCount === 0 && (
        <RegistryEmpty
          tasks={props.tasks}
          deferredQuery={props.deferredQuery}
          owner={props.owner}
          filter={props.filter}
          onCreate={props.onCreate}
        />
      )}
    </>
  );
}

import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {Pick<ReturnType<typeof import("./useTaskMonitorState").useTaskMonitorState>,"setSelected"|"setSelectedId"|"setEventStreamVersion"|"setActionError"|"loadTasks"|"loadSelected"|"updateListState"> & Pick<import("./taskMonitorContracts").TaskMonitorProps,"notify"|"onNavigate"|"onTaskFocus"> & {selected: AnalysisTask}} TaskActionContext */

/** @param {TaskActionContext} context */
export function taskLifecycleActions({
  notify,
  onNavigate,
  onTaskFocus,
  selected,
  setSelected,
  setSelectedId,
  setEventStreamVersion,
  setActionError,
  loadTasks,
  loadSelected,
  updateListState,
}) {
  return {
    onRename: async (/** @type {TaskPayload} */ payload) => {
      try {
        const updated = await taskMonitorApi.renameTask(selected.id, payload);
        setSelected(updated);
        await loadTasks();
        setEventStreamVersion((current) => current + 1);
        notify("任务名称已修改并记录操作人");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onCancel: async (/** @type {TaskPayload} */ payload) => {
      try {
        await taskMonitorApi.cancelTask(selected.id, payload);
        notify("取消请求已提交");
        await loadTasks();
        await loadSelected();
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onPause: async () => {
      try {
        const updated = await taskMonitorApi.pauseTask(selected.id, {
          expected_revision: selected.revision,
        });
        setSelected(updated);
        await loadTasks();
        notify("未完成 Listing 正在安全暂停");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onResume: async (/** @type {TaskPayload} */ payload) => {
      try {
        const updated = await taskMonitorApi.resumeTask(selected.id, payload);
        setSelected(updated);
        setActionError("");
        await loadTasks();
        updateListState({ filter: "active" });
        notify(
          selected.status === "cancelled"
            ? "未完成 Listing 已重新排队"
            : "未完成 Listing 已继续排队",
        );
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) {
          setActionError("任务版本已变化，请查看刷新后的状态再操作。");
          await loadSelected();
        }
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onRetry: async () => {
      try {
        const retried = await taskMonitorApi.retryTask(selected.id);
        await loadTasks();
        setSelectedId(retried.id);
        if (onTaskFocus) onTaskFocus(retried.id);
        else onNavigate("analysis-tasks", { kind: "task", id: retried.id });
        notify(
          selected.status === "completed"
            ? "已按原快照创建再次运行任务"
            : "重试任务已进入队列",
        );
      } catch (error) {
        notify(errorMessage(error), "error");
      }
    },
    onPreflightReplan: (/** @type {TaskPayload} */ payload) =>
      taskMonitorApi.preflightTaskReplan(selected.id, payload),
    onReplan: async (/** @type {TaskPayload} */ payload) => {
      try {
        const updated = await taskMonitorApi.replanTask(selected.id, payload);
        setSelected(updated);
        setActionError("");
        await loadTasks();
        notify("任务执行计划已更新");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) {
          setActionError("执行计划或任务版本已变化，请重新预检后再提交。");
          await loadSelected();
        }
        notify(errorMessage(error), "error");
        return false;
      }
    },
  };
}

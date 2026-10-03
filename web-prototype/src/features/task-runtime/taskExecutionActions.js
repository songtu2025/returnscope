import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/** @typedef {Pick<ReturnType<typeof import("./useTaskMonitorState").useTaskMonitorState>,"setSelected"|"setSelectedId"|"setEventStreamVersion"|"setActionError"|"loadTasks"|"loadSelected"|"updateListState"> & Pick<import("./taskMonitorContracts").TaskMonitorProps,"notify"|"onNavigate"|"onTaskFocus"> & {selected: AnalysisTask}} TaskActionContext */

/** @param {TaskActionContext} context */
export function taskExecutionActions({
  notify,
  selected,
  setSelected,
  setActionError,
  loadTasks,
  loadSelected,
}) {
  return {
    onRetrySegment: async (
      /** @type {string} */ segmentKey,
      /** @type {TaskPayload} */ payload,
    ) => {
      try {
        const updated = await taskMonitorApi.retryTaskSegment(
          selected.id,
          segmentKey,
          payload,
        );
        setSelected(updated);
        setActionError("");
        await loadTasks();
        notify("任务片段已重新排队");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) {
          setActionError("任务版本已变化，请查看刷新后的片段状态再操作。");
          await loadSelected();
        } else {
          setActionError(errorMessage(error));
        }
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onRetryResultPublish: async (/** @type {string} */ segmentId) => {
      try {
        const updated = await taskMonitorApi.retrySegmentResultPublish(
          selected.id,
          segmentId,
          {
            expected_revision: selected.revision,
            reason: "重新发布分类结果",
          },
        );
        setSelected(updated);
        setActionError("");
        await loadTasks();
        notify("分类结果正在重新生成");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onSegmentAction: async (
      /** @type {string} */ segmentKey,
      /** @type {SegmentAction} */ action,
      /** @type {string} */ note = "",
    ) => {
      try {
        const updated = await taskMonitorApi.controlTaskSegment(
          selected.id,
          segmentKey,
          action,
          {
            expected_revision: selected.revision,
            note,
          },
        );
        setSelected(updated);
        setActionError("");
        await loadTasks();
        notify(
          {
            pause: "Listing 暂停请求已提交",
            resume: "Listing 已重新进入等待队列",
            cancel: "Listing 取消请求已提交",
          }[action],
        );
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onParallelism: async (/** @type {number} */ maxParallelSegments) => {
      try {
        const updated = await taskMonitorApi.setTaskParallelism(selected.id, {
          expected_revision: selected.revision,
          max_parallel_segments: maxParallelSegments,
        });
        setSelected(updated);
        setActionError("");
        notify(`Listing 并行数已调整为 ${maxParallelSegments}`);
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) await loadSelected();
        notify(errorMessage(error), "error");
        return false;
      }
    },
    onReorderSegments: async (/** @type {string[]} */ segmentKeys) => {
      try {
        const updated = await taskMonitorApi.reorderTaskSegments(selected.id, {
          expected_revision: selected.revision,
          segment_keys: segmentKeys,
        });
        setSelected(updated);
        setActionError("");
        notify("执行顺序已更新，将在当前片段完成后生效");
        return true;
      } catch (error) {
        if (errorStatus(error) === 409) {
          setActionError("等待片段已经变化，请刷新后重新排序。");
          await loadSelected();
        }
        notify(errorMessage(error), "error");
        return false;
      }
    },
  };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus, Pulse } from "@phosphor-icons/react";
import { api } from "../../api";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { TaskDetail } from "./TaskDetail";
import { TaskRegistry } from "./TaskRegistry";
export function TaskMonitor({
  notify,
  onNavigate,
  onChanged,
  focusId,
  focusSegmentId = null,
}) {
  const [tasks, setTasks] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [eventStreamVersion, setEventStreamVersion] = useState(0);
  const [actionError, setActionError] = useState("");
  const selectedRequestGeneration = useRef(0);
  const previousFocusId = useRef(focusId);
  const listScroll = useRef(0);
  const [detailError, setDetailError] = useState("");

  const loadTasks = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      setListError("");
      try {
        const values = await api.tasks({ include_archived: true });
        setTasks(values);
      } catch (error) {
        setListError(error.message);
        if (!silent) notify(error.message, "error");
      } finally {
        setLoading(false);
      }
    },
    [notify],
  );

  const loadSelected = useCallback(
    async (options = {}) => {
      if (!selectedId) return null;
      const generation = ++selectedRequestGeneration.current;
      const value = await api.task(selectedId, options);
      if (selectedRequestGeneration.current === generation) setSelected(value);
      return value;
    },
    [selectedId],
  );

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);
  useEffect(() => {
    const previous = previousFocusId.current;
    previousFocusId.current = focusId;
    if (focusId) {
      setSelectedId(focusId);
      return;
    }
    if (previous) {
      setSelectedId(null);
    }
  }, [focusId]);
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setDetailError("");
    setActionError("");
    if (!selectedId) {
      selectedRequestGeneration.current += 1;
      setSelected(null);
      return () => controller.abort();
    }
    loadSelected({ signal: controller.signal }).catch((error) => {
      if (error.name !== "AbortError" && !controller.signal.aborted)
        setDetailError(error.message);
    });
    return () => {
      controller.abort();
      selectedRequestGeneration.current += 1;
    };
  }, [loadSelected, notify, selectedId]);
  useEffect(() => {
    if (!selectedId) return undefined;
    setEvents([]);
    let refreshTimer = null;
    let pendingEvents = [];
    const source = new EventSource(api.eventUrl(selectedId), {
      withCredentials: true,
    });
    source.addEventListener("task", (event) => {
      const value = JSON.parse(event.data);
      pendingEvents.push(value);
      if (refreshTimer !== null) return;
      refreshTimer = window.setTimeout(() => {
        refreshTimer = null;
        const nextEvents = pendingEvents;
        pendingEvents = [];
        setEvents((current) => [...current, ...nextEvents]);
        Promise.all([loadSelected(), loadTasks(true), onChanged()]).catch((error) =>
          notify(error.message, "error"),
        );
      }, 500);
    });
    source.addEventListener("close", () => source.close());
    return () => {
      source.close();
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    };
  }, [selectedId, eventStreamVersion, loadSelected, loadTasks, notify, onChanged]);

  useEffect(() => {
    if (selectedId) return undefined;
    const timer = window.setInterval(() => {
      if (!document.hidden) loadTasks(true);
    }, 10000);
    const frame = window.requestAnimationFrame(() =>
      window.scrollTo(0, listScroll.current),
    );
    return () => {
      window.clearInterval(timer);
      window.cancelAnimationFrame(frame);
    };
  }, [selectedId, loadTasks]);

  const showTaskDetail = Boolean(selectedId);
  const returnToList = () => {
    setSelectedId(null);
    onNavigate("analysis-tasks");
  };

  const archiveTasks = async (taskIds, archived) => {
    try {
      await api.archiveTasks(taskIds, archived);
      await loadTasks();
      if (selectedId && taskIds.includes(selectedId)) await loadSelected();
      notify(archived ? "任务已归档" : "任务已恢复");
      return true;
    } catch (error) {
      notify(error.message, "error");
      return false;
    }
  };

  return (
    <div className="standard-page task-page task-runtime-workspace">
      <div hidden={showTaskDetail}>
        <PageHeading
          title="分析任务"
          description="查看分析进展，处理问题，使用已有结果。"
          action={
            <button className="primary-button" onClick={() => onNavigate("new")}>
              <Plus size={18} />
              新建任务
            </button>
          }
        />
        <TaskRegistry
          tasks={tasks}
          selectedId={selectedId}
          filter={filter}
          onFilterChange={setFilter}
          loading={loading}
          error={listError}
          onReload={loadTasks}
          onCreate={() => onNavigate("new")}
          onOpen={(task) => {
            listScroll.current = window.scrollY;
            window.scrollTo(0, 0);
            setSelectedId(task.id);
            onNavigate("analysis-tasks", { kind: "task", id: task.id });
          }}
          onCreateSimilar={(task) =>
            onNavigate("new", { kind: "task-template", id: task.id })
          }
          onArchive={archiveTasks}
        />
      </div>
      {showTaskDetail && (
        <section className="task-detail-panel">
          <button className="task-back-button" onClick={returnToList}>
            <ArrowLeft size={17} /> 全部任务
          </button>
          {!selected && !detailError && <InlineLoading label="正在读取任务…" />}
          {!selected && detailError && (
            <EmptyState
              icon={Pulse}
              title="任务读取失败"
              description={detailError}
              action={
                <button
                  className="secondary-button"
                  onClick={() => {
                    setDetailError("");
                    loadSelected().catch((error) => setDetailError(error.message));
                  }}
                >
                  重新加载
                </button>
              }
            />
          )}
          {selected && (
            <TaskDetail
              key={selected.id}
              task={selected}
              onArchive={() => archiveTasks([selected.id], !selected.archived_at)}
              focusSegmentId={focusSegmentId}
              events={events}
              onViewClassification={(segment) =>
                onNavigate("classification-results", {
                  kind: "classification-result",
                  id: segment.result_version_id,
                  taskId: selected.id,
                  segmentId: segment.id || segment.segment_key,
                  listing: segment.scope?.listing,
                })
              }
              actionError={actionError}
              onClearActionError={() => setActionError("")}
              onRename={async (payload) => {
                try {
                  const updated = await api.renameTask(selected.id, payload);
                  setSelected(updated);
                  await loadTasks();
                  setEventStreamVersion((current) => current + 1);
                  notify("任务名称已修改并记录操作人");
                  return true;
                } catch (error) {
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onCancel={async (payload) => {
                try {
                  await api.cancelTask(selected.id, payload);
                  notify("取消请求已提交");
                  await loadTasks();
                  await loadSelected();
                  return true;
                } catch (error) {
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onPause={async () => {
                try {
                  const updated = await api.pauseTask(selected.id, {
                    expected_revision: selected.revision,
                  });
                  setSelected(updated);
                  await loadTasks();
                  notify("未完成 Listing 正在安全暂停");
                  return true;
                } catch (error) {
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onResume={async (payload) => {
                try {
                  const updated = await api.resumeTask(selected.id, payload);
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  setFilter("active");
                  notify(
                    selected.status === "cancelled"
                      ? "未完成 Listing 已重新排队"
                      : "未完成 Listing 已继续排队",
                  );
                  return true;
                } catch (error) {
                  if (error.status === 409) {
                    setActionError("任务版本已变化，请查看刷新后的状态再操作。");
                    await loadSelected();
                  }
                  notify(error.message, "error");
                  return false;
                }
              }}
              onRetry={async () => {
                try {
                  const retried = await api.retryTask(selected.id);
                  await loadTasks();
                  setSelectedId(retried.id);
                  onNavigate("analysis-tasks", { kind: "task", id: retried.id });
                  notify(
                    selected.status === "completed"
                      ? "已按原快照创建再次运行任务"
                      : "重试任务已进入队列",
                  );
                } catch (error) {
                  notify(error.message, "error");
                }
              }}
              onRetrySegment={async (segmentKey, payload) => {
                try {
                  const updated = await api.retryTaskSegment(
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
                  if (error.status === 409) {
                    setActionError("任务版本已变化，请查看刷新后的片段状态再操作。");
                    await loadSelected();
                  } else {
                    setActionError(error.message);
                  }
                  notify(error.message, "error");
                  return false;
                }
              }}
              onRetryResultPublish={async (segmentId) => {
                try {
                  const updated = await api.retrySegmentResultPublish(
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
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onSegmentAction={async (segmentKey, action, note = "") => {
                try {
                  const updated = await api.controlTaskSegment(
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
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onParallelism={async (maxParallelSegments) => {
                try {
                  const updated = await api.setTaskParallelism(selected.id, {
                    expected_revision: selected.revision,
                    max_parallel_segments: maxParallelSegments,
                  });
                  setSelected(updated);
                  setActionError("");
                  notify(`Listing 并行数已调整为 ${maxParallelSegments}`);
                  return true;
                } catch (error) {
                  if (error.status === 409) await loadSelected();
                  notify(error.message, "error");
                  return false;
                }
              }}
              onReorderSegments={async (segmentKeys) => {
                try {
                  const updated = await api.reorderTaskSegments(selected.id, {
                    expected_revision: selected.revision,
                    segment_keys: segmentKeys,
                  });
                  setSelected(updated);
                  setActionError("");
                  notify("执行顺序已更新，将在当前片段完成后生效");
                  return true;
                } catch (error) {
                  if (error.status === 409) {
                    setActionError("等待片段已经变化，请刷新后重新排序。");
                    await loadSelected();
                  }
                  notify(error.message, "error");
                  return false;
                }
              }}
              onPreflightReplan={(payload) =>
                api.preflightTaskReplan(selected.id, payload)
              }
              onReplan={async (payload) => {
                try {
                  const updated = await api.replanTask(selected.id, payload);
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  notify("任务执行计划已更新");
                  return true;
                } catch (error) {
                  if (error.status === 409) {
                    setActionError("执行计划或任务版本已变化，请重新预检后再提交。");
                    await loadSelected();
                  }
                  notify(error.message, "error");
                  return false;
                }
              }}
            />
          )}
        </section>
      )}
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { PlayCircle, Plus, Pulse, WarningCircle } from "@phosphor-icons/react";
import { api } from "../../api";
import {
  EmptyState,
  InlineLoading,
  PageHeading,
  StatusPill,
} from "../../components/SharedUi";
import { classNames, formatTime } from "../../lib/presentation";
import { TaskDetail } from "./TaskDetail";

const FINISHED_TASK_STATUSES = [
  "completed",
  "failed",
  "cancelled",
  "blocked",
  "partial",
];
const ACTIVE_TASK_STATUSES = ["queued", "running", "paused"];

function taskStatusLabel(task) {
  if (task.status === "cancelled" && task.result_file_path) {
    return "已取消（有部分结果）";
  }
  const executionPlan = task.snapshot?.execution_plan;
  const isPartialQueue =
    task.status === "queued" &&
    executionPlan?.unresolved_policy === "run_ready" &&
    executionPlan?.summary?.blocked_count > 0;
  return isPartialQueue ? "部分排队" : null;
}

function isActiveTask(task) {
  return ACTIVE_TASK_STATUSES.includes(task?.status);
}

function preferredActiveTaskId(tasks, currentId = null) {
  const currentTask = tasks.find((task) => task.id === currentId);
  if (isActiveTask(currentTask)) return currentId;
  return (
    tasks.find((task) => task.status === "running")?.id ??
    tasks.find(isActiveTask)?.id ??
    null
  );
}

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
  const [filter, setFilter] = useState("active");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [eventStreamVersion, setEventStreamVersion] = useState(0);
  const [actionError, setActionError] = useState("");
  const selectedRequestGeneration = useRef(0);
  const previousFocusId = useRef(focusId);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      const values = await api.tasks();
      setTasks(values);
      setSelectedId(
        (current) =>
          current ??
          values.find((task) => task.status === "running")?.id ??
          values.find(isActiveTask)?.id ??
          null,
      );
    } catch (error) {
      setListError(error.message);
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

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
      setFilter("all");
      setSelectedId(focusId);
      return;
    }
    if (previous) {
      setFilter("active");
      setSelectedId((current) => preferredActiveTaskId(tasks, current));
      setSelected((current) => (isActiveTask(current) ? current : null));
    }
  }, [focusId, tasks]);
  useEffect(() => {
    const controller = new AbortController();
    if (!selectedId) {
      selectedRequestGeneration.current += 1;
      setSelected(null);
      return () => controller.abort();
    }
    loadSelected({ signal: controller.signal }).catch((error) => {
      if (error.name !== "AbortError") notify(error.message, "error");
    });
    return () => controller.abort();
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
        setEvents((current) => [...current, ...nextEvents].slice(-100));
        Promise.all([loadSelected(), loadTasks(), onChanged()]).catch((error) =>
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
    if (filter === "active" && FINISHED_TASK_STATUSES.includes(selected?.status)) {
      setFilter("finished");
    }
  }, [filter, selected?.status]);

  const changeFilter = (value) => {
    setFilter(value);
    const matches = (task) => {
      if (value === "active") {
        return isActiveTask(task);
      }
      if (value === "finished") return FINISHED_TASK_STATUSES.includes(task.status);
      return true;
    };
    if (selected && !matches(selected)) {
      const replacement = tasks.find(matches);
      setSelectedId(replacement?.id ?? null);
      setSelected(null);
    }
  };

  const visibleTasks = tasks.filter((task) => {
    if (filter === "active") {
      return isActiveTask(task);
    }
    if (filter === "finished") return FINISHED_TASK_STATUSES.includes(task.status);
    return true;
  });
  const showTaskDetail = Boolean(focusId) || Boolean(selected) || tasks.length > 0;
  const isEmptyWorkspace = !showTaskDetail;

  return (
    <div className="standard-page task-page">
      <PageHeading
        eyebrow="实时任务工作台"
        title="分析任务"
        description="页面关闭后任务仍会在后台继续；重新进入时可恢复进度和完整日志。"
        action={
          <button className="primary-button" onClick={() => onNavigate("new")}>
            <Plus size={18} />
            新建任务
          </button>
        }
      />
      <div className={classNames("task-layout", isEmptyWorkspace && "is-empty")}>
        <section className="task-list-panel" aria-label="任务列表">
          <div className="segmented compact" aria-label="任务筛选">
            {[
              ["active", "进行中"],
              ["all", "全部"],
              ["finished", "已结束"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "active" : ""}
                onClick={() => changeFilter(value)}
                aria-pressed={filter === value}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="task-list-scroll">
            {loading && <InlineLoading label="读取任务…" />}
            {!loading && listError && (
              <div className="task-list-error" role="alert">
                <EmptyState
                  icon={WarningCircle}
                  title="任务列表读取失败"
                  description={listError}
                  action={
                    <button className="secondary-button" onClick={loadTasks}>
                      重新加载
                    </button>
                  }
                />
              </div>
            )}
            {!loading && !listError && visibleTasks.length === 0 && (
              <EmptyState
                icon={PlayCircle}
                title="暂无任务"
                description={
                  filter === "active"
                    ? "新任务开始后，会在这里展示实时进度、执行阶段和日志。"
                    : "创建任务后，会在这里保留完整的运行记录。"
                }
                action={
                  <button className="primary-button" onClick={() => onNavigate("new")}>
                    <Plus size={17} />
                    创建分析任务
                  </button>
                }
              />
            )}
            {!loading &&
              visibleTasks.map((task) => (
                <TaskListItem
                  key={task.id}
                  task={task}
                  active={selectedId === task.id}
                  onClick={() => {
                    setSelectedId(task.id);
                    onNavigate("analysis-tasks", { kind: "task", id: task.id });
                  }}
                />
              ))}
          </div>
        </section>
        {showTaskDetail && (
          <section className="task-detail-panel">
            {!selected && (
              <EmptyState
                icon={Pulse}
                title="选择一个任务"
                description="查看运行阶段、进度、日志和任务快照。"
              />
            )}
            {selected && (
              <TaskDetail
                task={selected}
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
    </div>
  );
}

function TaskListItem({ task, active, onClick }) {
  return (
    <button
      className={classNames("task-list-item", active && "active")}
      onClick={onClick}
      aria-pressed={active}
    >
      <div className="task-list-top">
        <StatusPill status={task.status} label={taskStatusLabel(task)} />
      </div>
      <b>{task.title}</b>
      <div className="task-list-meta">
        <time>{formatTime(task.created_at)}</time>
        <span>· {Math.round(task.progress_percent)}%</span>
      </div>
    </button>
  );
}
